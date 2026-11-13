/**
 * Regras puras de apresentação da tela, sem React, para serem testadas com
 * `node --test` (frontend/tests/). Tudo que decide O QUE a tela afirma mora
 * aqui: um rótulo errado ("ciphertexts iguais", "0 documentos" sem contexto)
 * contradiz a tese da PoV mesmo com o backend certo.
 */

export const brl = (n) => typeof n === 'number'
  ? n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
  : ''

export const formatarCpf = (cpf) => String(cpf).replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4')

/**
 * Onde o trecho buscado casou dentro do valor JÁ decifrado pela aplicação.
 *
 * Os campos de string do `encryptedFields` usam `caseSensitive: false`: o
 * servidor casa "TITULAR12" com "titular12@…". O destaque segue a mesma regra,
 * senão um resultado legítimo apareceria sem marca e pareceria falso positivo.
 * Devolve -1 quando o trecho não está na posição que o modo exige.
 */
export function posicaoDoTrecho(texto, trecho, modo) {
  const t = String(texto ?? '').toLowerCase()
  const q = String(trecho ?? '').toLowerCase()
  if (!q) return -1
  if (modo === 'prefixo') return t.startsWith(q) ? 0 : -1
  if (modo === 'sufixo') return t.endsWith(q) ? t.length - q.length : -1
  return t.indexOf(q)
}

/** Legenda de contagem de um painel; o lado sem chave sempre diz "sem a chave". */
export function legendaPainel(dados, destaque) {
  if (!dados) return ''
  const ms = typeof dados.ms === 'number' ? ` · ${dados.ms} ms` : ''
  if (destaque || typeof dados.ms !== 'number') return `${dados.encontrados} documento(s)${ms}`
  return `o mesmo filtro, sem a chave: ${dados.encontrados} documento(s)${ms}`
}

/**
 * O lado sem chave achou zero pelo filtro e a tela mostra os mesmos documentos
 * lidos por `_id`. Só vale para o painel do DBA: a aplicação nunca lê "por id".
 */
export const leituraPorId = (dados, destaque) => !destaque && dados?.origem === 'por_id'

/** Texto do ciphertext: amostra do PAYLOAD (nunca do cabeçalho de 17 bytes). */
export function textoCifra(valor) {
  if (!valor || typeof valor !== 'object' || !valor.__cifrado__) return null
  return {
    amostra: `${valor.hex}${valor.fim ? `…${valor.fim}` : '…'}`,
    rodape: `${valor.bytes} B · subtype 6${valor.chave ? ` · DEK ${valor.chave.slice(0, 8)}` : ''}`,
  }
}

const SENSITIVE = /(?:authorization|password|secret|token|uri|cpf|cnpj|email|salario|score|keymaterial|key)/i
// Rótulo que o backend dá ao ciphertext capturado na rede. Não é segredo — é a
// prova: mascará-lo esconderia justamente o que a tela quer mostrar.
const CIPHERTEXT = /^<Binary subtype 6 · \d+ B · ciphertext>$/

/** Mascara valores em claro sob chaves sensíveis, em qualquer profundidade. */
export function redact(value, key = '', sensitive = false) {
  const s = sensitive || SENSITIVE.test(key)
  if (typeof value === 'string' && CIPHERTEXT.test(value)) return value
  if (Array.isArray(value)) return value.map((item) => redact(item, '', s))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, redact(v, k, s)]))
  }
  return s ? '<mascarado>' : value
}

/**
 * Aviso de quantidade da busca de string: o total vem de um countDocuments com
 * o mesmo filtro cifrado. Sem total (falhou ou backend antigo) cai no limite.
 */
export function avisoTotalString(busca) {
  if (!busca?.aplicacao) return undefined
  const { encontrados, total } = busca.aplicacao
  if (typeof total === 'number' && total > encontrados) {
    return `${total.toLocaleString('pt-BR')} documentos casam no total; exibindo os primeiros ${encontrados}.`
  }
  if (typeof total !== 'number' && encontrados >= busca.limite) return `Exibindo os primeiros ${busca.limite}.`
  return undefined
}

/** Veredito do par plantado: só afirma "distintos" com dois ciphertexts lidos. */
export function vereditoPar(par) {
  if (!par) return null
  return par.ciphertexts_distintos
    ? { ok: true, icone: '✓', texto: par.leitura }
    : { ok: false, icone: '⚠️', texto: par.leitura }
}
