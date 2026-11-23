package io.github.lohanlilson.pons

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

/** Botão "Compartilhar → Pons" de qualquer app: manda direto para o computador. */
class Compartilhar : ComponentActivity() {
    private var titulo by mutableStateOf("Mandando ao computador…")
    private var progresso by mutableFloatStateOf(0f)

    @Suppress("DEPRECATION")
    private fun uris(i: Intent): List<Uri> = when (i.action) {
        Intent.ACTION_SEND -> listOfNotNull(
            if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java) else i.getParcelableExtra(Intent.EXTRA_STREAM))
        Intent.ACTION_SEND_MULTIPLE ->
            (if (Build.VERSION.SDK_INT >= 33) i.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
            else i.getParcelableArrayListExtra(Intent.EXTRA_STREAM)).orEmpty()
        else -> emptyList()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val con = Conexao(this)
        if (con.pc == null) {
            Toast.makeText(this, "Abra o Pons e pareie com o computador primeiro", Toast.LENGTH_LONG).show()
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }
        setContent {
            MaterialTheme(colorScheme = if (isSystemInDarkTheme()) darkColorScheme(primary = Color(0xFF9A74FF)) else lightColorScheme(primary = Color(0xFF6D3CF0))) {
                Card(Modifier.fillMaxWidth().padding(8.dp)) {
                    Column(Modifier.padding(20.dp)) {
                        Text(titulo, style = MaterialTheme.typography.titleMedium)
                        LinearProgressIndicator(progress = { progresso }, modifier = Modifier.fillMaxWidth().padding(top = 14.dp))
                    }
                }
            }
        }
        val lista = uris(intent)
        val texto = intent.getStringExtra(Intent.EXTRA_TEXT)
        lifecycleScope.launch {
            try {
                if (lista.isEmpty() && !texto.isNullOrBlank()) {
                    con.texto(texto)
                    Estado.registrar(this@Compartilhar, "Texto enviado ao PC: ${texto.take(100)}")
                    Toast.makeText(this@Compartilhar, "Texto copiado no computador", Toast.LENGTH_SHORT).show()
                } else {
                    lista.forEachIndexed { i, u ->
                        titulo = if (lista.size == 1) "Mandando ao computador…" else "Mandando ${i + 1} de ${lista.size}…"
                        val n = con.enviar(u) { progresso = it }
                        Estado.registrar(this@Compartilhar, "Enviado ao PC: $n")
                    }
                    Toast.makeText(this@Compartilhar, if (lista.size == 1) "Enviado ao computador" else "${lista.size} arquivos enviados",
                        Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@Compartilhar, "Não deu certo: ${e.message}", Toast.LENGTH_LONG).show()
            }
            finish()
        }
    }
}
