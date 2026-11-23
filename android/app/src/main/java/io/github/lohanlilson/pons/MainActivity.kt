package io.github.lohanlilson.pons

import android.Manifest
import android.app.Activity
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ContentPaste
import androidx.compose.material.icons.outlined.DocumentScanner
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.coroutines.resume

private val Violeta = Color(0xFF6D3CF0)
private val Ouro = Color(0xFFFFB547)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Estado.carregar(this)
        ServicoPons.canais(this)
        setContent {
            val escuro = isSystemInDarkTheme()
            MaterialTheme(colorScheme = if (escuro) darkColorScheme(primary = Color(0xFF9A74FF), secondary = Ouro)
            else lightColorScheme(primary = Violeta, secondary = Color(0xFFE08A1E))) {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) { Tela() }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        ServicoPons.ligar(this)
    }

    override fun onStop() {
        super.onStop()
        if (!getSharedPreferences("pons", Context.MODE_PRIVATE).getBoolean("segundo_plano", true)) ServicoPons.desligar(this)
    }
}

suspend fun lerCodigo(ctx: Context, formatos: IntArray): String? = suspendCancellableCoroutine { cont ->
    val opts = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(formatos[0], *formatos.drop(1).toIntArray())
        .enableAutoZoom().build()
    GmsBarcodeScanning.getClient(ctx, opts).startScan()
        .addOnSuccessListener { if (cont.isActive) cont.resume(it.rawValue) }
        .addOnCanceledListener { if (cont.isActive) cont.resume(null) }
        .addOnFailureListener { if (cont.isActive) cont.resume(null) }
}

/** Confere no GitHub se há versão nova do app (Release fixa "android"). */
suspend fun versaoNova(): Pair<String, String>? = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
    runCatching {
        val c = java.net.URL("https://github.com/lohanlilson/Pons/releases/download/android/versao.json").openConnection() as java.net.HttpURLConnection
        c.connectTimeout = 8000; c.readTimeout = 8000; c.instanceFollowRedirects = true
        val j = org.json.JSONObject(c.inputStream.bufferedReader().readText())
        if (j.optInt("codigo") > BuildConfig.VERSION_CODE) j.getString("versao") to j.getString("url") else null
    }.getOrNull()
}

@Composable
fun Tela() {
    val ctx = LocalContext.current
    val con = remember { Conexao(ctx) }
    var pc by remember { mutableStateOf(con.pc) }
    val conectado by Estado.conectado.collectAsState()
    val msg by Estado.mensagem.collectAsState()
    val hist by Estado.historico.collectAsState()
    val escopo = rememberCoroutineScope()
    var ocupado by remember { mutableStateOf<String?>(null) }
    var progresso by remember { mutableFloatStateOf(0f) }
    var erro by remember { mutableStateOf<String?>(null) }
    var config by remember { mutableStateOf(false) }
    var novaVersao by remember { mutableStateOf<Pair<String, String>?>(null) }
    LaunchedEffect(Unit) { novaVersao = versaoNova() }

    val pedirNotif = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 33) pedirNotif.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    fun enviar(uris: List<Uri>, tipo: String = "arquivo", nome: String? = null) {
        if (uris.isEmpty()) return
        escopo.launch {
            try {
                uris.forEachIndexed { i, u ->
                    ocupado = "Mandando ${i + 1} de ${uris.size}…"
                    progresso = 0f
                    val n = con.enviar(u, tipo, nome) { progresso = it }
                    Estado.registrar(ctx, "Enviado ao PC: $n")
                }
                Toast.makeText(ctx, if (uris.size == 1) "Enviado ao computador" else "${uris.size} arquivos enviados", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) { erro = e.message } finally { ocupado = null }
        }
    }

    val arquivos = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { enviar(it) }
    val fotos = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(50)) { enviar(it) }
    val scanner = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { r ->
        if (r.resultCode == Activity.RESULT_OK) {
            GmsDocumentScanningResult.fromActivityResultIntent(r.data)?.pdf?.uri?.let {
                val nome = "Documento " + SimpleDateFormat("yyyy-MM-dd HH-mm", Locale("pt", "BR")).format(Date()) + ".pdf"
                enviar(listOf(it), "scan", nome)
            }
        }
    }

    fun escanear() {
        val act = ctx as? Activity ?: return
        val opts = GmsDocumentScannerOptions.Builder().setGalleryImportAllowed(true).setPageLimit(50)
            .setResultFormats(GmsDocumentScannerOptions.RESULT_FORMAT_PDF).setScannerMode(GmsDocumentScannerOptions.SCANNER_MODE_FULL).build()
        GmsDocumentScanning.getClient(opts).getStartScanIntent(act)
            .addOnSuccessListener { scanner.launch(IntentSenderRequest.Builder(it).build()) }
            .addOnFailureListener { erro = "O scanner precisa do Google Play Services atualizado: ${it.message}" }
    }

    fun parear() {
        escopo.launch {
            val qr = lerCodigo(ctx, intArrayOf(Barcode.FORMAT_QR_CODE)) ?: return@launch
            try {
                ocupado = "Pareando…"
                val nome = con.parear(Protocolo.lerQr(qr))
                pc = con.pc
                ServicoPons.ligar(ctx)
                Estado.registrar(ctx, "Pareado com $nome")
                Toast.makeText(ctx, "Pareado com $nome", Toast.LENGTH_LONG).show()
            } catch (e: Exception) { erro = e.message } finally { ocupado = null }
        }
    }

    fun lerBoleto() {
        escopo.launch {
            val c = lerCodigo(ctx, intArrayOf(Barcode.FORMAT_ITF, Barcode.FORMAT_CODE_128, Barcode.FORMAT_QR_CODE)) ?: return@launch
            try {
                ocupado = "Mandando…"
                con.codigo(c, "")
                val d = Protocolo.descrever(c)
                Estado.registrar(ctx, "$d — enviado ao PC")
                Toast.makeText(ctx, "$d: já está copiado no computador", Toast.LENGTH_LONG).show()
            } catch (e: Exception) { erro = e.message } finally { ocupado = null }
        }
    }

    fun mandarCopiado() {
        val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val t = cm.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(ctx)?.toString()
        if (t.isNullOrBlank()) { erro = "Não há texto copiado no celular."; return }
        escopo.launch {
            try {
                con.texto(t)
                Estado.registrar(ctx, "Texto enviado ao PC: ${t.take(100)}")
                Toast.makeText(ctx, "Texto copiado no computador", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) { erro = e.message }
        }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        // cabeçalho
        Box(Modifier.fillMaxWidth().padding(16.dp).background(
            Brush.linearGradient(listOf(Color(0xFF2A1B6E), Violeta, Color(0xFFC0479B))), RoundedCornerShape(20.dp)).padding(20.dp)) {
            Column {
                Text("Pons", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(9.dp).background(if (conectado) Color(0xFF3ECF7A) else if (pc != null) Ouro else Color.White.copy(0.5f), CircleShape))
                    Spacer(Modifier.size(8.dp))
                    Text(when {
                        pc == null -> "Nenhum computador pareado"
                        conectado -> "Conectado a ${pc!!.nome}"
                        else -> "Procurando ${pc!!.nome}…"
                    }, color = Color.White.copy(0.9f))
                }
                if (!conectado && pc != null && msg.isNotBlank()) Text(msg, color = Color.White.copy(0.7f), fontSize = 12.sp)
            }
        }
        novaVersao?.let { (v, url) ->
            Card(onClick = { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp).padding(bottom = 10.dp),
                colors = CardDefaults.cardColors(containerColor = Ouro.copy(alpha = 0.22f))) {
                Text("Pons $v disponível — toque para baixar", Modifier.padding(14.dp), fontWeight = FontWeight.SemiBold)
            }
        }
        if (ocupado != null) {
            Column(Modifier.padding(horizontal = 16.dp)) {
                Text(ocupado!!, style = MaterialTheme.typography.bodySmall)
                LinearProgressIndicator(progress = { progresso }, modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp))
            }
        }
        if (pc == null) {
            Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("No computador, abra o Pons e clique em “Parear celular”. Depois toque abaixo e aponte a câmera para o código.",
                    style = MaterialTheme.typography.bodyLarge)
                Spacer(Modifier.height(20.dp))
                Button(onClick = { parear() }, modifier = Modifier.fillMaxWidth().height(56.dp)) {
                    Icon(Icons.Outlined.QrCodeScanner, null)
                    Spacer(Modifier.size(10.dp))
                    Text("Parear com computador", fontSize = 16.sp)
                }
                Spacer(Modifier.height(12.dp))
                Text("O celular e o computador precisam estar no mesmo Wi-Fi.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall)
            }
            return@Column
        }
        // ações
        Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Acao(Icons.Outlined.DocumentScanner, "Escanear documento", "vira PDF no PC", Modifier.weight(1f)) { escanear() }
                Acao(Icons.Outlined.QrCodeScanner, "Ler boleto ou nota", "copia no PC", Modifier.weight(1f)) { lerBoleto() }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Acao(Icons.Outlined.Image, "Mandar fotos", "e vídeos", Modifier.weight(1f)) {
                    fotos.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
                }
                Acao(Icons.Outlined.FolderOpen, "Mandar arquivos", "PDF, planilhas…", Modifier.weight(1f)) { arquivos.launch("*/*") }
            }
            Acao(Icons.Outlined.ContentPaste, "Mandar o texto copiado", "cola no computador com Ctrl+V", Modifier.fillMaxWidth()) { mandarCopiado() }
        }
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Histórico", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            TextButton(onClick = { config = true }) { Text("Configurações") }
        }
        val fmt = remember { SimpleDateFormat("dd/MM HH:mm", Locale("pt", "BR")) }
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
            if (hist.isEmpty()) item {
                Text("Também dá para mandar pelo botão Compartilhar de qualquer app: escolha “Pons”.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(8.dp))
            }
            items(hist) { h ->
                Column(Modifier.fillMaxWidth().clickable(enabled = h.uri != null) {
                    runCatching {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse(h.uri), h.mime ?: "*/*")
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                    }
                }.padding(vertical = 8.dp, horizontal = 4.dp)) {
                    Text(h.texto, style = MaterialTheme.typography.bodyMedium)
                    Text(fmt.format(Date(h.quando)), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }

    if (config) Configuracoes(con, onFechar = { config = false; pc = con.pc }, onParear = { config = false; parear() })
    erro?.let { e ->
        AlertDialog(onDismissRequest = { erro = null }, confirmButton = { TextButton(onClick = { erro = null }) { Text("OK") } },
            title = { Text("Não deu certo") }, text = { Text(e) })
    }
}

@Composable
fun Acao(icone: ImageVector, titulo: String, sub: String, modifier: Modifier, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = modifier, shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icone, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(28.dp))
            Spacer(Modifier.size(12.dp))
            Column {
                Text(titulo, fontWeight = FontWeight.SemiBold)
                Text(sub, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

fun permissaoNotificacoes(ctx: Context): Boolean {
    val lista = Settings.Secure.getString(ctx.contentResolver, "enabled_notification_listeners") ?: return false
    return lista.contains(ComponentName(ctx, NotificacoesPons::class.java).flattenToString())
}

@Composable
fun Configuracoes(con: Conexao, onFechar: () -> Unit, onParear: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = ctx.getSharedPreferences("pons", Context.MODE_PRIVATE)
    var notif by remember { mutableStateOf(prefs.getBoolean("notificacoes", false) && permissaoNotificacoes(ctx)) }
    var fundo by remember { mutableStateOf(prefs.getBoolean("segundo_plano", true)) }
    var esquecer by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onFechar, confirmButton = { TextButton(onClick = onFechar) { Text("Fechar") } },
        title = { Text("Configurações") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Mostrar as notificações no PC")
                        Text("WhatsApp, banco, SMS… aparecem no computador", style = MaterialTheme.typography.bodySmall)
                    }
                    Switch(checked = notif, onCheckedChange = {
                        notif = it
                        prefs.edit().putBoolean("notificacoes", it).apply()
                        if (it && !permissaoNotificacoes(ctx)) {
                            Toast.makeText(ctx, "Ative o Pons na lista que vai abrir", Toast.LENGTH_LONG).show()
                            ctx.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                        }
                    })
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Receber com o app fechado")
                        Text("Textos, arquivos e “tocar o celular” chegam a qualquer hora", style = MaterialTheme.typography.bodySmall)
                    }
                    Switch(checked = fundo, onCheckedChange = { fundo = it; prefs.edit().putBoolean("segundo_plano", it).apply() })
                }
                Text("Computador: ${con.pc?.nome ?: "nenhum"}", fontWeight = FontWeight.SemiBold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onParear) { Text("Parear outro") }
                    OutlinedButton(onClick = { esquecer = true }) { Text("Esquecer") }
                }
                Text("Pons ${BuildConfig.VERSION_NAME} · tudo passa só pela sua rede Wi-Fi, cifrado.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        })
    if (esquecer) {
        val escopo = rememberCoroutineScope()
        AlertDialog(onDismissRequest = { esquecer = false },
            confirmButton = {
                TextButton(onClick = {
                    escopo.launch {
                        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { con.esquecer() }
                        ServicoPons.desligar(ctx)
                        esquecer = false
                        onFechar()
                    }
                }) { Text("Esquecer") }
            },
            dismissButton = { TextButton(onClick = { esquecer = false }) { Text("Cancelar") } },
            title = { Text("Esquecer o computador?") }, text = { Text("Para usar de novo, será preciso parear pelo QR.") })
    }
}
