package io.github.lohanlilson.pons

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.Ringtone
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.IBinder
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.MediaStore
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.webkit.MimeTypeMap
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.FileProvider
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors

/** Estado compartilhado entre a tela e o serviço. */
object Estado {
    val conectado = MutableStateFlow(false)
    val mensagem = MutableStateFlow("")
    private val _historico = MutableStateFlow<List<Item>>(emptyList())
    val historico: StateFlow<List<Item>> = _historico

    data class Item(val quando: Long, val texto: String, val uri: String? = null, val mime: String? = null)

    fun carregar(ctx: Context) {
        val s = ctx.getSharedPreferences("pons", Context.MODE_PRIVATE).getString("historico", "[]")
        _historico.value = runCatching {
            val a = JSONArray(s)
            (0 until a.length()).map { a.getJSONObject(it) }.map {
                Item(it.getLong("q"), it.getString("t"), it.optString("u").ifEmpty { null }, it.optString("m").ifEmpty { null })
            }
        }.getOrDefault(emptyList())
    }

    fun registrar(ctx: Context, texto: String, uri: Uri? = null, mime: String? = null) {
        val novo = (listOf(Item(System.currentTimeMillis(), texto, uri?.toString(), mime)) + _historico.value).take(60)
        _historico.value = novo
        val a = JSONArray()
        novo.forEach { a.put(JSONObject().put("q", it.quando).put("t", it.texto).put("u", it.uri ?: "").put("m", it.mime ?: "")) }
        ctx.getSharedPreferences("pons", Context.MODE_PRIVATE).edit().putString("historico", a.toString()).apply()
    }
}

/** Fica ligado ao PC (avisa o que chega: texto, arquivo, "tocar o celular"). */
class ServicoPons : Service() {
    private var rodando = false
    private var toque: Ringtone? = null
    private val pool = Executors.newSingleThreadExecutor()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACAO_PARAR_TOQUE) {
            pararToque()
            return START_STICKY
        }
        if (intent?.action == ACAO_DESLIGAR) {
            rodando = false
            stopSelf()
            return START_NOT_STICKY
        }
        canais(this)
        val n = NotificationCompat.Builder(this, CANAL_CONEXAO)
            .setSmallIcon(R.drawable.ic_notificacao)
            .setContentTitle("Pons ligado ao computador")
            .setContentText("Recebe textos e arquivos do PC")
            .setOngoing(true)
            .setContentIntent(abrirApp(this))
            .build()
        val tipo = if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE else 0
        ServiceCompat.startForeground(this, 1, n, tipo)
        if (!rodando) {
            rodando = true
            Thread(::laco, "pons-eventos").start()
        }
        return START_STICKY
    }

    private fun laco() {
        val con = Conexao(this)
        val prefs = getSharedPreferences("pons", Context.MODE_PRIVATE)
        var desde = prefs.getLong("desde", 0)
        var espera = 2000L
        while (rodando) {
            if (con.pc == null) { Estado.conectado.value = false; break }
            try {
                val r = con.eventos(desde)
                Estado.conectado.value = true
                Estado.mensagem.value = ""
                espera = 2000
                val evs = r.getJSONArray("eventos")
                for (i in 0 until evs.length()) tratar(con, evs.getJSONObject(i))
                desde = r.optLong("ultimo", desde)
                prefs.edit().putLong("desde", desde).apply()
            } catch (e: java.net.SocketTimeoutException) {
                // espera longa sem novidade: normal
            } catch (e: Exception) {
                Estado.conectado.value = false
                Estado.mensagem.value = e.message ?: "sem conexão"
                if (e.message?.contains("relógio") == true || e.message?.contains("chave") == true) desde = 0
                Thread.sleep(espera)
                espera = (espera * 2).coerceAtMost(30000)
            }
        }
        Estado.conectado.value = false
        stopSelf()
    }

    private fun tratar(con: Conexao, ev: JSONObject) {
        when (ev.optString("tipo")) {
            "texto" -> {
                val t = ev.optString("texto")
                android.os.Handler(mainLooper).post {
                    (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("Pons", t))
                }
                avisar("Texto do computador copiado", t.take(200), null)
                Estado.registrar(this, "Texto do PC: ${t.take(120)}")
            }
            "arquivo" -> {
                val nome = ev.optString("nome", "arquivo")
                val (uri, saida) = criarArquivo(nome)
                try {
                    saida.use { con.baixar(ev, it) }
                    finalizar(uri)
                    val mime = mimeDe(nome)
                    avisar("Arquivo do computador recebido", "$nome — toque para abrir", abrirArquivo(uri, mime))
                    Estado.registrar(this, "Recebido do PC: $nome", uri, mime)
                } catch (e: Exception) {
                    runCatching { contentResolver.delete(uri, null, null) }
                    avisar("Não foi possível receber $nome", e.message ?: "", null)
                }
            }
            "tocar" -> tocar()
        }
    }

    private fun mimeDe(nome: String) =
        MimeTypeMap.getSingleton().getMimeTypeFromExtension(nome.substringAfterLast('.', "").lowercase()) ?: "application/octet-stream"

    /** Downloads/Pons (Android 10+) ou a pasta do app (Android 8 e 9). */
    private fun criarArquivo(nome: String): Pair<Uri, java.io.OutputStream> {
        if (Build.VERSION.SDK_INT >= 29) {
            val v = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, nome)
                put(MediaStore.Downloads.MIME_TYPE, mimeDe(nome))
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Pons")
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v) ?: throw Protocolo.Erro("sem espaço para salvar")
            return uri to (contentResolver.openOutputStream(uri) ?: throw Protocolo.Erro("não consegui salvar"))
        }
        val pasta = File(getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "Pons").apply { mkdirs() }
        var f = File(pasta, nome)
        var n = 2
        while (f.exists()) { f = File(pasta, nome.substringBeforeLast('.') + " ($n)." + nome.substringAfterLast('.', "")); n++ }
        val uri = FileProvider.getUriForFile(this, "$packageName.arquivos", f)
        return uri to f.outputStream()
    }

    private fun finalizar(uri: Uri) {
        if (Build.VERSION.SDK_INT >= 29 && uri.authority == MediaStore.AUTHORITY) {
            contentResolver.update(uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null)
        }
    }

    private fun abrirArquivo(uri: Uri, mime: String): PendingIntent {
        val i = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        return PendingIntent.getActivity(this, uri.hashCode(), Intent.createChooser(i, "Abrir com").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    private fun avisar(titulo: String, texto: String, acao: PendingIntent?) {
        val n = NotificationCompat.Builder(this, CANAL_RECEBIDOS)
            .setSmallIcon(R.drawable.ic_notificacao)
            .setContentTitle(titulo)
            .setContentText(texto)
            .setStyle(NotificationCompat.BigTextStyle().bigText(texto))
            .setAutoCancel(true)
            .setContentIntent(acao ?: abrirApp(this))
            .build()
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify((System.currentTimeMillis() % 100000).toInt() + 10, n)
    }

    private fun tocar() {
        android.os.Handler(mainLooper).post {
            pararToque()
            val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM) ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            toque = RingtoneManager.getRingtone(this, uri)?.apply {
                audioAttributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
                if (Build.VERSION.SDK_INT >= 28) isLooping = true
                play()
            }
            val vib = getSystemService(VIBRATOR_SERVICE) as Vibrator
            vib.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 600, 400), 0))
            val parar = PendingIntent.getService(this, 2, Intent(this, ServicoPons::class.java).setAction(ACAO_PARAR_TOQUE),
                PendingIntent.FLAG_IMMUTABLE)
            val n = NotificationCompat.Builder(this, CANAL_TOQUE)
                .setSmallIcon(R.drawable.ic_notificacao)
                .setContentTitle("Achei você!")
                .setContentText("O computador pediu para o celular tocar. Toque para parar.")
                .setContentIntent(parar)
                .setDeleteIntent(parar)
                .addAction(0, "Parar", parar)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .build()
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(3, n)
            android.os.Handler(mainLooper).postDelayed({ pararToque() }, 60_000)
        }
    }

    private fun pararToque() {
        toque?.stop()
        toque = null
        (getSystemService(VIBRATOR_SERVICE) as Vibrator).cancel()
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).cancel(3)
    }

    override fun onDestroy() {
        rodando = false
        pararToque()
        pool.shutdown()
        super.onDestroy()
    }

    companion object {
        const val CANAL_CONEXAO = "conexao"
        const val CANAL_RECEBIDOS = "recebidos"
        const val CANAL_TOQUE = "tocar"
        const val ACAO_PARAR_TOQUE = "parar_toque"
        const val ACAO_DESLIGAR = "desligar"

        fun canais(ctx: Context) {
            val nm = ctx.getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(NotificationChannel(CANAL_CONEXAO, "Conexão com o computador", NotificationManager.IMPORTANCE_MIN))
            nm.createNotificationChannel(NotificationChannel(CANAL_RECEBIDOS, "Recebidos do computador", NotificationManager.IMPORTANCE_HIGH))
            nm.createNotificationChannel(NotificationChannel(CANAL_TOQUE, "Tocar o celular", NotificationManager.IMPORTANCE_HIGH).apply {
                setBypassDnd(true)
            })
        }

        fun abrirApp(ctx: Context): PendingIntent = PendingIntent.getActivity(ctx, 0,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)

        fun ligar(ctx: Context) {
            if (Conexao(ctx).pc == null) return
            runCatching { ctx.startForegroundService(Intent(ctx, ServicoPons::class.java)) }
        }

        fun desligar(ctx: Context) {
            runCatching { ctx.startService(Intent(ctx, ServicoPons::class.java).setAction(ACAO_DESLIGAR)) }
        }
    }
}

/** Mostra no computador as notificações do celular (só se a pessoa ligar e der a permissão). */
class NotificacoesPons : NotificationListenerService() {
    private val pool = Executors.newSingleThreadExecutor()
    private var ultima = ""

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val prefs = getSharedPreferences("pons", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("notificacoes", false) || sbn.packageName == packageName || sbn.isOngoing) return
        val ex = sbn.notification.extras
        if ((sbn.notification.flags and Notification.FLAG_GROUP_SUMMARY) != 0) return
        val titulo = ex.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: return
        val texto = (ex.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: ex.getCharSequence(Notification.EXTRA_TEXT))?.toString() ?: ""
        val chave = "${sbn.packageName}|$titulo|$texto"
        if (chave == ultima) return
        ultima = chave
        val app = runCatching { packageManager.getApplicationLabel(packageManager.getApplicationInfo(sbn.packageName, 0)).toString() }
            .getOrDefault(sbn.packageName)
        pool.execute { runCatching { Conexao(this).notificacao(app, titulo, texto) } }
    }

    override fun onDestroy() {
        pool.shutdown()
        super.onDestroy()
    }
}
