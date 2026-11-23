package io.github.lohanlilson.pons

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** Vetores gerados pelo programa do PC (pons/protocolo.py): garante que os dois lados falam a mesma língua. */
class ProtocoloTest {
    private val chave = ByteArray(32) { it.toByte() }

    @Test fun chaveBase64() = assertArrayEquals(chave, Protocolo.b64d("AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"))

    @Test fun abreMensagemDoPc() {
        val m = Protocolo.abrir(chave, "jBiClomL522NY9MoZaO_GYdO7UoUSFOJ-Z5veQe1XziJBLPqXT6tMRsh65YKpIY03dQZYCffsSpB0jyGZCL3RBjYL0H3y1PwGOTvTLI5DzIIHPb-65W2_qjXLoxAn7M")
        assertEquals("texto", m.getString("tipo"))
        assertEquals("Olá, ação ✓", m.getString("texto"))
    }

    @Test fun parteComAad() {
        val p = Protocolo.b64d("QdXB9B8oYxT95h8Ad1uOBtjtQmH5g7Sh-jLwICNrIoCWmPdyYxlgSRN02RU9zi4")
        assertEquals("conteudo do arquivo", String(Protocolo.decifrar(chave, p, Protocolo.aadParte("abc", 3))))
        try { Protocolo.decifrar(chave, p, Protocolo.aadParte("abc", 4)); fail("parte trocada deveria falhar") } catch (_: Protocolo.Erro) {}
    }

    @Test fun idaEVolta() {
        val s = Protocolo.selar(chave, JSONObject().put("a", 1))
        val m = Protocolo.abrir(chave, s)
        assertEquals(1, m.getInt("a"))
        assertTrue(m.getLong("ts") > 0)
        try { Protocolo.abrir(ByteArray(32), s); fail("chave errada deveria falhar") } catch (_: Protocolo.Erro) {}
    }

    @Test fun qrDoPc() {
        val p = Protocolo.lerQr("pons://parear?h=192.168.0.10,10.0.0.5&p=47802&id=pc123&n=Escrit%C3%B3rio%20Lohan&k=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8")
        assertEquals(listOf("192.168.0.10", "10.0.0.5"), p.ips)
        assertEquals(47802, p.porta)
        assertEquals("pc123", p.id)
        assertEquals("Escritório Lohan", p.nome)
        assertArrayEquals(chave, p.chave)
        try { Protocolo.lerQr("https://exemplo.com"); fail() } catch (_: Protocolo.Erro) {}
    }

    @Test fun descreveCodigos() {
        // linha digitável de boleto Itaú de exemplo (R$ 1.234,56)
        val barras = "3419" + "1000" + "0000123456" + "1121234567890100000000000"
        val bar = barras.substring(0, 4) + dv(barras) + barras.substring(4)
        assertTrue(Protocolo.descrever(bar).contains("1.234,56"))
        assertEquals("Conta de consumo ou tributo", Protocolo.descrever("8" + "1".repeat(47)))
        assertEquals("PIX copia e cola", Protocolo.descrever("00020126580014br.gov.bcb.pix"))
    }

    private fun dv(semDv: String): Char {
        var soma = 0; var peso = 2
        for (c in semDv.reversed()) { soma += (c - '0') * peso; peso = if (peso == 9) 2 else peso + 1 }
        val r = 11 - soma % 11
        return if (r == 0 || r == 10 || r == 11) '1' else '0' + r
    }
}
