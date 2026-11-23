package io.github.lohanlilson.pons

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Liga o serviço quando o celular reinicia ou o app é atualizado. */
class Inicio : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (ctx.getSharedPreferences("pons", Context.MODE_PRIVATE).getBoolean("segundo_plano", true)) ServicoPons.ligar(ctx)
    }
}
