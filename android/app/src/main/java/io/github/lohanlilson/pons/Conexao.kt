package io.github.lohanlilson.pons

import android.content.Context
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.OutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.SocketTimeoutException
import java.net.URL
import java.security.MessageDigest
import java.util.UUID

/** Computador pareado e conversa com ele (o celular sempre é quem conecta). */
class Conexao(private val ctx: Context) {
    private val prefs = ctx.getSharedPreferences("pons", Context.MODE_PRIVATE)

    val idDisp: String = prefs.getString("id_disp", null) ?: UUID.randomUUID().toString().replace("-", "").take(16).also {
        prefs.edit().putString("id_disp", it).apply()
    }

    data class Pc(val id: String, val nome: String, val ip: String, val porta: Int, val chave: ByteArray)

    /** Lido sempre das preferências: a tela, o serviço e o leitor de notificações veem a mesma coisa. */
    val pc: Pc? get() = carregar()

    private fun carregar(): Pc? {
        val s = prefs.getString("pc", null) ?: return null
        return runCatching {
            val j = JSONObject(s)
            Pc(j.getString("id"), j.getString("nome"), j.getString("ip"), j.getInt("porta"), Protocolo.b64d(j.getString("chave")))
        }.getOrNull()
    }

    private fun salvar(p: Pc?) {
        prefs.edit().apply {
            if (p == null) remove("pc").remove("desde") else putString("pc", JSONObject().put("id", p.id).put("nome", p.nome).put("ip", p.ip)
                .put("porta", p.porta).put("chave", Protocolo.b64e(p.chave)).toString())
        }.apply()
    }

    fun nomeCelular(): String = prefs.getString("nome", null) ?: (Build.MANUFACTURER.replaceFirstChar { it.uppercase() } + " " + Build.MODEL)

    // ---------------------------------------------------------------- HTTP
    private fun abrirConexao(base: String, caminho: String, metodo: String, timeoutLeitura: Int): HttpURLConnection =
        (URL(base + caminho).openConnection() as HttpURLConnection).apply {
            requestMethod = metodo
            connectTimeout = 5000
            readTimeout = timeoutLeitura
            setRequestProperty("X-Pons-Disp", idDisp)
            setRequestProperty("Content-Type", "application/octet-stream")
        }

    private fun requisitar(base: String, caminho: String, corpo: ByteArray?, timeoutLeitura: Int = 40000): ByteArray {
        val c = abrirConexao(base, caminho, if (corpo != null) "POST" else "GET", timeoutLeitura)
        try {
            if (corpo != null) {
                c.doOutput = true
                c.setFixedLengthStreamingMode(corpo.size)
                c.outputStream.use { it.write(corpo) }
            }
            val codigo = c.responseCode
            if (codigo != 200) {
                val msg = c.errorStream?.bufferedReader()?.readText()?.takeIf { it.isNotBlank() } ?: "erro $codigo"
                if (codigo == 403 && msg.contains("não pareado")) {
                    salvar(null)
                    throw Protocolo.Erro("O computador esqueceu este celular. Pareie de novo.")
                }
                throw Protocolo.Erro(msg)
            }
            return c.inputStream.use { it.readBytes() }
        } finally { c.disconnect() }
    }

    /** Pedido ao PC; se o endereço mudou (Wi-Fi trocou o IP), procura o PC na rede e tenta de novo. */
    private fun pedir(caminho: String, corpo: ByteArray?, timeoutLeitura: Int = 40000): ByteArray {
        val p = pc ?: throw Protocolo.Erro("Nenhum computador pareado")
        return try {
            requisitar("http://${p.ip}:${p.porta}", caminho, corpo, timeoutLeitura)
        } catch (e: java.io.IOException) {
            if (e is SocketTimeoutException && caminho == "/v1/eventos") throw e
            val achado = procurar(p.id, 4000) ?: throw Protocolo.Erro("Computador não encontrado na rede. Ele está ligado, com o Pons aberto e no mesmo Wi-Fi?")
            salvar(p.copy(ip = achado.first, porta = achado.second))
            requisitar("http://${achado.first}:${achado.second}", caminho, corpo, timeoutLeitura)
        }
    }

    private fun msg(caminho: String, obj: JSONObject, timeoutLeitura: Int = 40000): JSONObject {
        val p = pc ?: throw Protocolo.Erro("Nenhum computador pareado")
        return Protocolo.abrir(p.chave, String(pedir(caminho, Protocolo.selar(p.chave, obj).toByteArray(), timeoutLeitura)))
    }

    /** Escuta os anúncios do PC (UDP) até achar o id. Devolve (ip, porta). */
    fun procurar(idPc: String, ms: Int): Pair<String, Int>? {
        val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val trava = wifi.createMulticastLock("pons").apply { setReferenceCounted(false); acquire() }
        try {
            DatagramSocket(null).use { s ->
                s.reuseAddress = true
                s.broadcast = true
                s.bind(InetSocketAddress(Protocolo.PORTA_UDP))
                val fim = System.currentTimeMillis() + ms
                val buf = ByteArray(2048)
                while (System.currentTimeMillis() < fim) {
                    s.soTimeout = (fim - System.currentTimeMillis()).toInt().coerceAtLeast(1)
                    val pk = DatagramPacket(buf, buf.size)
                    try { s.receive(pk) } catch (_: SocketTimeoutException) { break }
                    val j = runCatching { JSONObject(String(pk.data, 0, pk.length)) }.getOrNull() ?: continue
                    if (j.optString("app") == "pons" && j.optString("id") == idPc) return pk.address.hostAddress!! to j.optInt("porta", 47800)
                }
            }
        } catch (_: Exception) {
        } finally { trava.release() }
        return null
    }

    // ---------------------------------------------------------------- ações
    suspend fun parear(p: Protocolo.Pareamento): String = withContext(Dispatchers.IO) {
        var ultimoErro: Exception? = null
        for (ip in p.ips + listOfNotNull(procurar(p.id, 3000)?.first)) {
            try {
                val corpo = Protocolo.selar(p.chave, JSONObject().put("nome", nomeCelular()).put("modelo", Build.MODEL))
                val r = Protocolo.abrir(p.chave, String(requisitar("http://$ip:${p.porta}", "/v1/parear", corpo.toByteArray(), 15000)))
                if (r.optBoolean("ok")) {
                    salvar(Pc(p.id, r.optString("nome_pc", p.nome), ip, p.porta, p.chave))
                    return@withContext r.optString("nome_pc", p.nome)
                }
            } catch (e: Exception) { ultimoErro = e }
        }
        throw Protocolo.Erro(when (ultimoErro) {
            is Protocolo.Erro -> ultimoErro.message ?: "Não foi possível parear"
            else -> "Não achei o computador. Confira se os dois estão no mesmo Wi-Fi."
        })
    }

    fun esquecer() {
        runCatching { msg("/v1/msg", JSONObject().put("tipo", "sair"), 5000) }
        salvar(null)
    }

    suspend fun texto(t: String) = withContext(Dispatchers.IO) { msg("/v1/msg", JSONObject().put("tipo", "texto").put("texto", t)) }

    suspend fun codigo(valor: String, formato: String) = withContext(Dispatchers.IO) {
        msg("/v1/msg", JSONObject().put("tipo", "codigo").put("valor", valor).put("formato", formato))
    }

    fun notificacao(app: String, titulo: String, texto: String) {
        msg("/v1/msg", JSONObject().put("tipo", "notificacao").put("app", app).put("titulo", titulo).put("texto", texto), 8000)
    }

    fun nomeArquivo(uri: Uri): Pair<String, Long> {
        var nome = "arquivo"
        var tam = -1L
        ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                c.getString(0)?.let { nome = it }
                if (!c.isNull(1)) tam = c.getLong(1)
            }
        }
        return nome to tam
    }

    /** Manda um arquivo (foto, PDF…) em partes cifradas. tipo = "arquivo" ou "scan". */
    suspend fun enviar(uri: Uri, tipo: String = "arquivo", nome: String? = null, progresso: (Float) -> Unit = {}): String =
        withContext(Dispatchers.IO) {
            val p = pc ?: throw Protocolo.Erro("Nenhum computador pareado")
            val (nomeReal, tamanho) = nomeArquivo(uri)
            val nomeFinal = nome ?: nomeReal
            val ini = msg("/v1/up/inicio", JSONObject().put("nome", nomeFinal).put("tamanho", tamanho).put("tipo", tipo))
            val id = ini.getString("id")
            val sha = MessageDigest.getInstance("SHA-256")
            var enviado = 0L
            ctx.contentResolver.openInputStream(uri)?.use { ent ->
                val buf = ByteArray(Protocolo.PEDACO)
                var i = 0
                while (true) {
                    var n = 0
                    while (n < buf.size) {
                        val r = ent.read(buf, n, buf.size - n)
                        if (r < 0) break
                        n += r
                    }
                    if (n == 0 && i > 0) break
                    val parte = buf.copyOf(n)
                    sha.update(parte)
                    val atual = pc ?: p
                    Protocolo.abrir(atual.chave, String(pedir("/v1/up/parte?id=$id&i=$i", Protocolo.cifrar(atual.chave, parte, Protocolo.aadParte(id, i)))))
                    enviado += n
                    if (tamanho > 0) progresso((enviado.toFloat() / tamanho).coerceAtMost(1f))
                    i++
                    if (n < buf.size) break
                }
            } ?: throw Protocolo.Erro("Não consegui ler o arquivo")
            val fim = msg("/v1/up/fim", JSONObject().put("id", id).put("sha256", sha.digest().joinToString("") { "%02x".format(it) }))
            fim.optString("nome", nomeFinal)
        }

    /** Espera eventos do PC (texto, arquivo, tocar) — chamado em laço pelo serviço. */
    fun eventos(desde: Long, espera: Int = 25): JSONObject =
        msg("/v1/eventos", JSONObject().put("desde", desde).put("espera", espera), (espera + 15) * 1000)

    fun baixar(ev: JSONObject, saida: OutputStream, progresso: (Float) -> Unit = {}) {
        val p = pc ?: throw Protocolo.Erro("Nenhum computador pareado")
        val id = ev.getString("id")
        val partes = ev.getInt("partes")
        val sha = MessageDigest.getInstance("SHA-256")
        for (i in 0 until partes) {
            val dados = Protocolo.decifrar(p.chave, pedir("/v1/baixar?id=$id&i=$i", null), Protocolo.aadParte(id, i))
            sha.update(dados)
            saida.write(dados)
            progresso((i + 1f) / partes)
        }
        val h = sha.digest().joinToString("") { "%02x".format(it) }
        if (h != ev.optString("sha256")) throw Protocolo.Erro("O arquivo chegou corrompido")
    }
}
