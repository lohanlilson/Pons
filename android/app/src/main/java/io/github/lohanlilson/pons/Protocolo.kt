package io.github.lohanlilson.pons

import org.json.JSONObject
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** O mesmo protocolo do programa do PC (pons/protocolo.py): AES-256-GCM com a chave lida no QR. */
object Protocolo {
    const val PORTA_UDP = 47801
    const val PEDACO = 2 * 1024 * 1024
    private val rnd = SecureRandom()

    class Erro(msg: String) : Exception(msg)

    fun b64e(b: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(b)
    fun b64d(s: String): ByteArray = Base64.getUrlDecoder().decode(s.trim().trimEnd('='))

    fun cifrar(chave: ByteArray, dados: ByteArray, aad: ByteArray? = null): ByteArray {
        val nonce = ByteArray(12).also { rnd.nextBytes(it) }
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, SecretKeySpec(chave, "AES"), GCMParameterSpec(128, nonce))
        if (aad != null) c.updateAAD(aad)
        return nonce + c.doFinal(dados)
    }

    fun decifrar(chave: ByteArray, pacote: ByteArray, aad: ByteArray? = null): ByteArray {
        if (pacote.size < 28) throw Erro("resposta curta")
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, SecretKeySpec(chave, "AES"), GCMParameterSpec(128, pacote, 0, 12))
        if (aad != null) c.updateAAD(aad)
        return try { c.doFinal(pacote, 12, pacote.size - 12) } catch (e: Exception) { throw Erro("chave errada ou dados alterados") }
    }

    fun selar(chave: ByteArray, obj: JSONObject): String {
        obj.put("ts", System.currentTimeMillis())
        return b64e(cifrar(chave, obj.toString().toByteArray()))
    }

    fun abrir(chave: ByteArray, texto: String): JSONObject = JSONObject(String(decifrar(chave, b64d(texto))))

    fun aadParte(id: String, i: Int) = "$id:$i".toByteArray()

    data class Pareamento(val ips: List<String>, val porta: Int, val id: String, val nome: String, val chave: ByteArray)

    /** pons://parear?h=IP1,IP2&p=PORTA&id=ID&n=NOME&k=CHAVE */
    fun lerQr(texto: String): Pareamento {
        val t = texto.trim()
        if (!t.startsWith("pons://parear")) throw Erro("Esse não é o QR do Pons. Abra o Pons no computador e clique em “Parear celular”.")
        val q = t.substringAfter('?', "").split('&').filter { '=' in it }.associate {
            it.substringBefore('=') to java.net.URLDecoder.decode(it.substringAfter('='), "UTF-8")
        }
        val ips = q["h"]?.split(",")?.filter { it.isNotBlank() }?.takeIf { it.isNotEmpty() } ?: throw Erro("QR incompleto")
        return Pareamento(ips, q["p"]?.toIntOrNull() ?: 47800, q["id"] ?: throw Erro("QR incompleto"),
            q["n"] ?: "Computador", b64d(q["k"] ?: throw Erro("QR incompleto")))
    }

    // ---------------------------------------------------------------- o que a câmera leu (para mostrar no celular)
    fun descrever(codigo: String): String {
        val d = codigo.filter { it.isDigit() }
        return when {
            (d.length == 44 || d.length == 47) && !d.startsWith("8") -> {
                val barras = if (d.length == 44) d else d.substring(0, 4) + d[32] + d.substring(33, 47) + d.substring(4, 9) + d.substring(10, 20) + d.substring(21, 31)
                val valor = barras.substring(9, 19).toLong() / 100.0
                "Boleto de R$ " + String.format(java.util.Locale("pt", "BR"), "%,.2f", valor)
            }
            d.startsWith("8") && (d.length == 44 || d.length == 48) -> "Conta de consumo ou tributo"
            Regex("(?<!\\d)\\d{44}(?!\\d)").containsMatchIn(codigo.replace(" ", "")) -> "Nota fiscal (chave de acesso)"
            codigo.startsWith("000201") -> "PIX copia e cola"
            codigo.startsWith("http") -> "Link"
            else -> "Código"
        }
    }
}
