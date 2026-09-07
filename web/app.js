/* Porch Light — Spec 6 web surface.
 *
 * Render logic adapted from the accepted mock (design/porch-light-ui-v1.html).
 * The frozen parts (COPY, i18n switch, state toggle, ARIA behaviors) are copied.
 * The "expected to change" parts (ui-contract.md) are the deliberate deltas:
 *   1. Storage: the watchlist lives in localStorage AND the URL fragment (never a
 *      query string, never server-side) — never.md #8.
 *   2. Data source: changed cards render from sample.json (real stored 3685/3687
 *      items), not inline sample arrays — §25 path swap.
 *   3. City: Ventura, not Riverdale.
 *   4. No send capability anywhere (never.md #4).
 *   5. Shared watch links are shown and CONFIRMED before applying, never auto-applied.
 */
"use strict";

/* ---- state ---- */
let language = "en";
let activeState = "quiet";
let watches = [];          // [{text, lang}] — from localStorage / URL fragment
let drafts = [];           // [{title:{en,es}, edited:{en,es}}]
let changed = [];          // real items loaded from sample.json
// The corpus window carried AS DATA by whichever engine answered: the live
// /api/watch response (Aurora's real earliest/latest meeting_date + doc count) or,
// on the sample/keyword-fallback path, sample.json's own `window` field. NEVER
// parsed out of rendered receipt text, never guessed. Shape: {en, es} display
// strings, or null when no window is available (then the note is not rendered).
let corpusWindow = null;
const commentDraft = { position: "", matters: "", ask: "" };
let commentDraftSaved = false;
let scaffoldOpenId = null; // which card's scaffold is open, if any

const WATCH_KEY = "porchlight.watches.v1";
const DRAFTS_KEY = "porchlight.drafts.v1";
const MAX_TERMS = 10;
const MAX_TERM_CHARS = 100;   // mirrors watch/validate.py (raised from 60; see there)
// The city's authoritative pages. Both verified resolving 2026-09-06. Notify Me is
// the city's OWN notification service — Porch Light sends nothing, so it points here.
const CITY_AGENDA_URL = "https://www.cityofventura.ca.gov/AgendaCenter";
const CITY_NOTIFY_URL = "https://www.cityofventura.ca.gov/list.aspx";
// The window carried by sample.json (fallback path). Set in loadChanged from the
// file's own `window` field — never parsed out of receipt text.
let sampleWindow = null;

/* Turn a corpus-window object {earliest, latest, document_count} (ISO date strings
 * COPIED from source, e.g. "2026-08-17") into bilingual display strings, or null.
 * Dates are formatted for display only; none are generated (never.md #1). Uses the
 * browser's Intl date formatter per language, parsing the ISO date as local noon so
 * a timezone offset can never roll it to the previous day. */
function formatWindow(win) {
  if (!win || !win.earliest || !win.latest) return null;
  const fmt = (iso, loc) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
    if (!m) return null;
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12, 0, 0);
    if (isNaN(d.getTime())) return null;
    return new Intl.DateTimeFormat(loc, { year: "numeric", month: "short", day: "numeric" }).format(d);
  };
  const enFrom = fmt(win.earliest, "en-US"), enTo = fmt(win.latest, "en-US");
  const esFrom = fmt(win.earliest, "es-ES"), esTo = fmt(win.latest, "es-ES");
  if (!enFrom || !enTo || !esFrom || !esTo) return null;
  const enRange = enFrom === enTo ? enFrom : `${enFrom} \u2013 ${enTo}`;
  const esRange = esFrom === esTo ? esFrom : `${esFrom} \u2013 ${esTo}`;
  // Honest coverage: meetings with a READABLE agenda over meetings in the window
  // (the gap is cancellations, which have nothing to extract). Appended only when
  // both counts are present — never a document count, never guessed.
  const wi = win.meetings_with_items, mt = win.meetings_total;
  if (Number.isFinite(wi) && Number.isFinite(mt) && mt > 0) {
    return {
      en: `${enRange} (${wi} of ${mt} meetings with a readable agenda)`,
      es: `${esRange} (${wi} de ${mt} reuniones con una agenda legible)`,
    };
  }
  return { en: enRange, es: esRange };
}

/* ---- copy (bilingual, verbatim strings load-bearing) ---- */
const COPY = {
  en: {
    skip: "Skip to main content", navLabel: "Primary navigation", languageLabel: "Language",
    navQuiet: "Quiet week", navChanges: "Changed", navCalendar: "Calendar", navBodies: "All bodies", navHow: "How it works",
    navUnavailable: "(not available in this preview)",
    sample: "Real City of Ventura agenda items, read and verified by Porch Light.",
    greeting: "Good afternoon, neighbor.",
    tagline: "City changes, brought home. A quiet agent for public agendas.",
    heartbeatTitle: "System heartbeat",
    cityRead: "City read from stored agendas", readCount: "2 meetings read", nextCheck: "We fetch new agendas hourly.",
    quietTitle: "Nothing new for you this week.",
    quietBody: "We read the City Council and Planning Commission agendas we hold. Nothing matched what you're watching. Your watch list lives only in this browser, so check back and run it again anytime.",
    windowNote: "The agendas we currently hold cover {window}.",
    onboardTitle: "Your week is quiet until you add a watch.",
    onboardBody: "We read the City Council and Planning Commission agendas we hold and broke them into items. Nothing can match until you add a watch above. Your watch list lives only in this browser, and Porch Light checks it against the agendas we hold when you ask.",
    scaleNote: "Porch Light breaks each agenda into individual items and points every summary back to its page.",
    quietStateLoaded: "Quiet week view shown.", changedStateLoaded: "Changed view shown.",
    changedTitle: "Real agenda items, read and verified.",
    changedIntro: "Items Porch Light read from the city's agendas, each pointing back to its source page.",
    changesRegion: "Agenda items read from the city record",
    fallbackNote: "Shown as published by the city — a verified plain summary could not be produced.",
    startComment: "Start a comment",
    scaffoldRegion: "Comment draft scaffold", scaffoldTitle: "Porch Light fills in the facts. The words are yours.",
    scaffoldIntro: "Review the sourced facts, then write only the parts that belong to you.",
    filledTitle: "Filled in for you, from the source",
    factAboutLabel: "What this is about", factMeetingLabel: "Which meeting", factReceiptLabel: "Receipt",
    yoursTitle: "Yours to write", positionLabel: "Your position", mattersLabel: "Why this matters to you", askLabel: "What you are asking for",
    scaffoldNote: "Porch Light never writes your opinion and cannot send anything. When you're done, you copy this and send it yourself.",
    saveDraft: "Save draft", closeScaffold: "Close", draftSavedFromChange: "Draft saved in your drafts panel.",
    draftNotStored: "Added to this session, but your browser blocked storage, so it will not survive a reload.",
    recentChecks: "Recent checks", checksRegion: "Recent checks and source status",
    history: "See full check history", historyClose: "Hide full check history",
    historyLines: ["Hourly checks run on schedule.", "Change detection has fired on a real changed document."],
    packetHeading: "The last thing we read", sourceLabel: "Original source document as published by the city.", packetSummary: "Open the source document",
    packetCaption: "One recent agenda, shown as the city published it \u2014 not everything we hold. Add a watch above to see matches across every agenda we've read.",
    toolsRegion: "Your drafts and writing tools", watchRegion: "Start and manage watches",
    watchKicker: "Start here", watchTitle: "Tell Porch Light what matters.",
    watchIntro: "Describe a project, place, concern, or question in your own words. Porch Light checks the public record and brings back relevant changes.",
    watchLabel: "Ask a question, or name a thing you want watched", watchPlaceholder: "Can they put a bar next to my house?",
    exampleIntro: "For example:", exampleAnd: "or", countSuffix: " / 100 characters",
    // FALLBACK copy (not shown unless the live-wire attempt is abandoned; see
    // KNOWN-LIMITATIONS "Watcher relevance in the web demo"). Wired only in the
    // fallback posture so a judge is never misled that the browser ran the model.
    demoScope: "This demo checks your watch against agenda items Porch Light has already read and verified.",
    clearAll: "Clear everything on this device",
    clearConfirm: "Clear your watch list, drafts, and this link's shared terms from this device? This cannot be undone.",
    clearYes: "Clear everything", clearNo: "Keep my data", cleared: "Cleared. This device is back to a fresh start.",
    startWatching: "Start watching",
    helper: "Porch Light checks this against the agenda items we hold, each time you ask. It cannot notify you, and your list stays in this browser.",
    saved: "Currently watching",
    firstRunTitle: "Start with one thing you care about.",
    firstRunBody: "A watch can be a question (\u201cCan they put a bar next to my house?\u201d) or a phrase (\u201cstreet trees on Juniper Avenue\u201d). Porch Light checks it against the agenda items we hold, each time you ask. Type your own words above.",
    privacy: "Your list stays on your device. We use it to answer, and never store it.",
    draftTitle: "Drafts are yours to finish and send.",
    draftExplainer: "Porch Light fills in the facts and the deadline from the source. The opinion is yours to write, and only you can send it.",
    startDraft: "\uFF0B Start a draft",
    remove: "Remove watch", added: "Watch added.", empty: "Enter something you want Porch Light to watch.",
    matchCountOne: "1 item matches what you're watching.", matchCountMany: "{n} items match what you're watching.",
    noMatchTitle: "Nothing matches that yet.", noMatchBody: "We read the agendas we hold and found nothing matching \u201C{term}\u201D. Porch Light checks only when you ask, and your watch list stays in this browser.",
    notifyNote: "Porch Light does not send notifications. The city's own Notify Me does.",
    notifyLink: "Sign up for the city's Notify Me",
    checkingLive: "Checking the live watcher\u2026",
    modeLive: "Matched by the live Nova Lite watcher, reading the city's agenda items.",
    modeKeyword: "Matched by keyword against agenda items Porch Light has already read and verified.",
    modeFallback: "The live watcher was unavailable, so this matched by keyword against items Porch Light has already read and verified.",
    tooLong: "That's a bit long. Try shortening it to 100 characters or fewer.", tooMany: "You can watch up to 10 things. Remove one to add another.", duplicate: "You're already watching that.",
    draftAdded: "A blank draft was added.", untitledDraft: "Untitled public comment", editedNow: "Edited now",
    shareConfirm: "A shared list was found in this link. Apply it? This replaces your current list.",
    shareApply: "Apply shared list", shareDismiss: "Keep my list", shareApplied: "Shared list applied.", shareDismissed: "Kept your list.",
    aboutTitle: "What this is",
    aboutBody: "Porch Light reads the public agenda packets your city posts and breaks them into individual items, then checks them against your watch list when you ask. Every summary points back to the page it came from. It drafts. You write your position, and you decide whether to send it.",
    limitsTitle: "What it does not do",
    limitOne: "It never scores, grades, or ranks a public body.",
    limitTwo: "It never sends anything to a government office. There is no send button anywhere in the code.",
    limitThree: "It never generates a date, a deadline, an item number, or a page range. Those are copied from the source or not shown.",
    limitFour: "It never stores your watch list. That list lives on your device.",
    disclaimerTitle: "Independent project",
    disclaimer: "Porch Light is an independent project. It is not affiliated with, endorsed by, or operated by any city or public agency. Always confirm dates and deadlines against the city's own posting.",
    builtTitle: "Built by", built: "Built by Shara Cordero. AI assisted. Human approved. Powered by NLP.",
    linksTitle: "Links", linkedinPending: "LinkedIn \u00B7 URL to be supplied", sourcePending: "Source code \u00B7 URL to be supplied",
    cityAgenda: "The city's own agenda page",
    footerProto: "Porch Light is a prototype built for the AWS Agents for Humans hackathon. It is not affiliated with or endorsed by the City of Ventura.",
    footerRunning: "This site is running through October 2026.",
    footerSource: "The city's Agenda Center is the authoritative source.",
    footerSourceLink: "Open the city's Agenda Center",
    footerRewrites: "Rewrites are AI-generated and human-approved. Check the receipt."
  },
  es: {
    skip: "Saltar al contenido principal", navLabel: "Navegaci\u00F3n principal", languageLabel: "Idioma",
    navQuiet: "Semana tranquila", navChanges: "Cambios", navCalendar: "Calendario", navBodies: "Todos los organismos", navHow: "C\u00F3mo funciona",
    navUnavailable: "(no disponible en esta vista previa)",
    sample: "Puntos reales de la agenda de la Ciudad de Ventura, le\u00EDdos y verificados por Porch Light.",
    greeting: "Buenas tardes, vecindad.",
    tagline: "Los cambios de la ciudad, a su puerta. Un agente discreto para las agendas p\u00FAblicas.",
    heartbeatTitle: "Estado del sistema",
    cityRead: "Ciudad le\u00EDda de agendas almacenadas", readCount: "2 reuniones le\u00EDdas", nextCheck: "Obtenemos nuevas agendas cada hora.",
    quietTitle: "Nada nuevo para usted esta semana.",
    quietBody: "Le\u00EDmos las agendas del Concejo Municipal y de la Comisi\u00F3n de Planificaci\u00F3n que tenemos. Nada coincidi\u00F3 con lo que usted sigue. Su lista de temas vive solo en este navegador; vuelva y ej\u00E9cutela de nuevo cuando quiera.",
    windowNote: "Las agendas que tenemos actualmente cubren {window}.",
    onboardTitle: "Su semana est\u00E1 tranquila hasta que agregue un tema.",
    onboardBody: "Le\u00EDmos las agendas del Concejo Municipal y de la Comisi\u00F3n de Planificaci\u00F3n que tenemos y las dividimos en puntos. Nada puede coincidir hasta que agregue un tema arriba. Su lista de temas vive solo en este navegador, y Porch Light la compara con las agendas que tenemos cuando usted lo pide.",
    scaleNote: "Porch Light divide cada agenda en puntos individuales y remite cada resumen a su p\u00E1gina.",
    quietStateLoaded: "Se muestra la vista de semana tranquila.", changedStateLoaded: "Se muestra la vista de cambios.",
    changedTitle: "Puntos reales de la agenda, le\u00EDdos y verificados.",
    changedIntro: "Puntos que Porch Light ley\u00F3 de las agendas de la ciudad, cada uno con enlace a su p\u00E1gina de origen.",
    changesRegion: "Puntos de la agenda le\u00EDdos del registro de la ciudad",
    fallbackNote: "Mostrado tal como lo public\u00F3 la ciudad: no se pudo producir un resumen verificado.",
    startComment: "Iniciar un comentario",
    scaffoldRegion: "Estructura del borrador de comentario", scaffoldTitle: "Porch Light completa los hechos. Las palabras son suyas.",
    scaffoldIntro: "Revise los hechos obtenidos de la fuente y luego escriba solamente las partes que le corresponden.",
    filledTitle: "Completado para usted, a partir de la fuente",
    factAboutLabel: "De qu\u00E9 se trata", factMeetingLabel: "Qu\u00E9 reuni\u00F3n", factReceiptLabel: "Comprobante",
    yoursTitle: "Para que usted lo escriba", positionLabel: "Su posici\u00F3n", mattersLabel: "Por qu\u00E9 esto le importa", askLabel: "Lo que est\u00E1 solicitando",
    scaffoldNote: "Porch Light nunca escribe su opini\u00F3n y no puede enviar nada. Cuando termine, copie el texto y env\u00EDelo usted mismo.",
    saveDraft: "Guardar borrador", closeScaffold: "Cerrar", draftSavedFromChange: "El borrador se guard\u00F3 en su panel de borradores.",
    draftNotStored: "Se agreg\u00F3 en esta sesi\u00F3n, pero su navegador bloque\u00F3 el almacenamiento, as\u00ED que no sobrevivir\u00E1 a una recarga.",
    recentChecks: "Revisiones recientes", checksRegion: "Revisiones recientes y estado de las fuentes",
    history: "Ver historial completo", historyClose: "Ocultar historial completo",
    historyLines: ["Las revisiones por hora se ejecutan seg\u00FAn lo programado.", "La detecci\u00F3n de cambios se activ\u00F3 en un documento real modificado."],
    packetHeading: "Lo \u00FAltimo que le\u00EDmos", sourceLabel: "Documento fuente original tal como lo public\u00F3 la ciudad.", packetSummary: "Abrir el documento fuente",
    packetCaption: "Una agenda reciente, tal como la public\u00F3 la ciudad, no todo lo que tenemos. Agregue un tema arriba para ver coincidencias en todas las agendas que hemos le\u00EDdo.",
    toolsRegion: "Sus borradores y herramientas de escritura", watchRegion: "Iniciar y administrar temas de seguimiento",
    watchKicker: "Empiece aqu\u00ED", watchTitle: "D\u00EDgale a Porch Light lo que le importa.",
    watchIntro: "Describa un proyecto, lugar, inquietud o pregunta con sus propias palabras. Porch Light revisa el registro p\u00FAblico y le presenta los cambios pertinentes.",
    watchLabel: "Haga una pregunta o nombre algo que quiera vigilar", watchPlaceholder: "\u00BFPueden poner un bar al lado de mi casa?",
    exampleIntro: "Por ejemplo:", exampleAnd: "o", countSuffix: " / 100 caracteres",
    demoScope: "Esta demostraci\u00F3n compara su tema con los asuntos de la agenda que Porch Light ya ley\u00F3 y verific\u00F3.",
    clearAll: "Borrar todo en este dispositivo",
    clearConfirm: "\u00BFBorrar su lista de temas, sus borradores y los temas compartidos de este enlace de este dispositivo? Esto no se puede deshacer.",
    clearYes: "Borrar todo", clearNo: "Conservar mis datos", cleared: "Borrado. Este dispositivo vuelve a empezar de cero.",
    startWatching: "Empezar a vigilar",
    helper: "Porch Light compara esto con los asuntos de la agenda que tenemos, cada vez que usted lo pide. No puede avisarle, y su lista permanece en este navegador.",
    saved: "En seguimiento",
    firstRunTitle: "Empiece con algo que le importe.",
    firstRunBody: "Un tema puede ser una pregunta (\u201c\u00BFPueden poner un bar al lado de mi casa?\u201D) o una frase (\u201c\u00E1rboles en la avenida Juniper\u201D). Porch Light lo compara con los asuntos de la agenda que tenemos, cada vez que usted lo pide. Escriba sus propias palabras arriba.",
    privacy: "Su lista permanece en su dispositivo. La usamos para responderle y nunca la guardamos.",
    draftTitle: "Usted termina y env\u00EDa sus borradores.",
    draftExplainer: "Porch Light completa los hechos y el plazo a partir de la fuente. La opini\u00F3n la escribe usted y solamente usted puede enviarla.",
    startDraft: "\uFF0B Iniciar un borrador",
    remove: "Eliminar tema", added: "Tema agregado.", empty: "Escriba algo que desea que Porch Light vigile.",
    matchCountOne: "1 punto coincide con lo que usted sigue.", matchCountMany: "{n} puntos coinciden con lo que usted sigue.",
    noMatchTitle: "Todav\u00EDa no hay coincidencias.", noMatchBody: "Le\u00EDmos las agendas que tenemos y no encontramos nada que coincida con \u201C{term}\u201D. Porch Light revisa solo cuando usted lo pide, y su lista de temas permanece en este navegador.",
    notifyNote: "Porch Light no env\u00EDa notificaciones. El servicio Notify Me de la ciudad s\u00ED lo hace.",
    notifyLink: "Suscr\u00EDbase al Notify Me de la ciudad",
    checkingLive: "Consultando el watcher en vivo\u2026",
    modeLive: "Coincidencia del watcher Nova Lite en vivo, leyendo los asuntos de la agenda de la ciudad.",
    modeKeyword: "Coincidencia por palabra clave con los asuntos de la agenda que Porch Light ya ley\u00F3 y verific\u00F3.",
    modeFallback: "El watcher en vivo no estuvo disponible, as\u00ED que la coincidencia fue por palabra clave con los asuntos que Porch Light ya ley\u00F3 y verific\u00F3.",
    tooLong: "Es un poco largo. Int\u00E9ntelo con 100 caracteres o menos.", tooMany: "Puede vigilar hasta 10 cosas. Elimine uno para agregar otro.", duplicate: "Ya est\u00E1 vigilando eso.",
    draftAdded: "Se agreg\u00F3 un borrador en blanco.", untitledDraft: "Comentario p\u00FAblico sin t\u00EDtulo", editedNow: "Editado ahora",
    shareConfirm: "Se encontr\u00F3 una lista compartida en este enlace. \u00BFAplicarla? Esto reemplaza su lista actual.",
    shareApply: "Aplicar lista compartida", shareDismiss: "Conservar mi lista", shareApplied: "Lista compartida aplicada.", shareDismissed: "Conserv\u00F3 su lista.",
    aboutTitle: "Qu\u00E9 es esto",
    aboutBody: "Porch Light lee los paquetes de agendas p\u00FAblicas que publica su ciudad y los divide en asuntos individuales, y luego los compara con su lista de temas cuando usted lo pide. Cada resumen remite a la p\u00E1gina de la que proviene. Prepara borradores. Usted escribe su posici\u00F3n y decide si desea enviarla.",
    limitsTitle: "Qu\u00E9 no hace",
    limitOne: "Nunca punt\u00FAa, califica ni clasifica a un organismo p\u00FAblico.",
    limitTwo: "Nunca env\u00EDa nada a una oficina gubernamental. No hay ning\u00FAn bot\u00F3n para enviar en el c\u00F3digo.",
    limitThree: "Nunca genera una fecha, un plazo, un n\u00FAmero de asunto ni un rango de p\u00E1ginas. Esos datos se copian de la fuente o no se muestran.",
    limitFour: "Nunca almacena su lista de temas. Esa lista vive en su dispositivo.",
    disclaimerTitle: "Proyecto independiente",
    disclaimer: "Porch Light es un proyecto independiente. No est\u00E1 afiliado, respaldado ni operado por ninguna ciudad ni organismo p\u00FAblico. Confirme siempre las fechas y los plazos en la publicaci\u00F3n oficial de la ciudad.",
    builtTitle: "Creado por", built: "Creado por Shara Cordero. Con asistencia de IA. Aprobado por una persona. Impulsado por PLN.",
    linksTitle: "Enlaces", linkedinPending: "LinkedIn \u00B7 URL pendiente", sourcePending: "C\u00F3digo fuente \u00B7 URL pendiente",
    cityAgenda: "P\u00E1gina oficial de agendas de la ciudad",
    footerProto: "Porch Light es un prototipo creado para el hackathon AWS Agents for Humans. No est\u00E1 afiliado ni respaldado por la Ciudad de Ventura.",
    footerRunning: "Este sitio est\u00E1 disponible hasta octubre de 2026.",
    footerSource: "El Agenda Center de la ciudad es la fuente autorizada.",
    footerSourceLink: "Abrir el Agenda Center de la ciudad",
    footerRewrites: "Las reescrituras son generadas por IA y aprobadas por una persona. Verifique el comprobante."
  }
};

const t = (key) => COPY[language][key];

/* ---- watchlist storage: localStorage + URL fragment, never server-side ---- */
function normalizeTerm(s) { return String(s == null ? "" : s).trim(); }

function loadWatchesFromStorage() {
  try {
    const raw = localStorage.getItem(WATCH_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((w) => w && typeof w.text === "string") : [];
  } catch { return []; }
}
function saveWatchesToStorage() {
  try { localStorage.setItem(WATCH_KEY, JSON.stringify(watches)); } catch { /* storage may be blocked; the list still lives in memory */ }
  syncFragment();
}

/* Drafts persist to localStorage, per-device, versioned like the watchlist. A draft
 * holds what the person wrote; it NEVER goes server-side (never.md #8), same as the
 * watch list. Every read/write is wrapped: a browser with storage blocked still
 * renders and still lets someone write a draft this session — but saveDraftsToStorage
 * returns whether the write actually landed, so the UI can tell the truth instead of
 * claiming a save that did not happen. */
function loadDraftsFromStorage() {
  try {
    const raw = localStorage.getItem(DRAFTS_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    // Keep only well-formed rows: {title:{en,es}, edited:{en,es}}.
    return Array.isArray(arr)
      ? arr.filter((d) => d && d.title && typeof d.title.en === "string" && typeof d.title.es === "string")
      : [];
  } catch { return []; }
}
function saveDraftsToStorage() {
  try {
    localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts));
    return true;
  } catch {
    // Storage blocked/full: the draft still lives in memory for this session, but we
    // did NOT persist it. Return false so the caller does not claim it saved.
    return false;
  }
}
/* The share link carries terms in the URL FRAGMENT (never a query string, never
 * sent to a server). It is only WRITTEN here; applying an incoming one is always
 * shown-and-confirmed (never auto-applied). */
function syncFragment() {
  const terms = watches.map((w) => w.text);
  const frag = terms.length ? "w=" + encodeURIComponent(JSON.stringify(terms)) : "";
  const url = location.pathname + location.search + (frag ? "#" + frag : "");
  history.replaceState(null, "", url);
}
function parseFragmentTerms() {
  const h = location.hash.replace(/^#/, "");
  const m = /(?:^|&)w=([^&]*)/.exec(h);
  if (!m) return null;
  try {
    const arr = JSON.parse(decodeURIComponent(m[1]));
    if (!Array.isArray(arr)) return null;
    return arr.map(normalizeTerm).filter(Boolean).slice(0, MAX_TERMS);
  } catch { return null; }
}

/* Client-side validation MIRRORS the server (watch/validate.py): 10 terms, 60
 * chars, printable, no control chars. Never trust the front end — but also never
 * ship a term the server would reject. */
function validateNewTerm(term) {
  if (!term) return "empty";
  if (term.length > MAX_TERM_CHARS) return "tooLong";
  if (/[\u0000-\u001F\u007F]/.test(term)) return "empty";
  if (watches.length >= MAX_TERMS) return "tooMany";
  if (watches.some((w) => w.text.toLocaleLowerCase() === term.toLocaleLowerCase())) return "duplicate";
  return null;
}

/* ---- helpers ---- */
function copyNode(tag, className, key) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  n.textContent = t(key);
  n.lang = language;
  return n;
}
function setStatus(id, msg) {
  const n = document.getElementById(id);
  if (!n) return;
  n.textContent = msg || "";
  n.lang = language;
}

/* ---- relevance: which stored items match the watchlist ----
 * TRANSPARENT keyword match for the static demo — NOT the model. The real relevance
 * decision is the watcher agent (watch/matcher.py), which runs server-side against
 * Aurora; wiring the browser to it is deferred (task 8.2). Here, an item matches a
 * term if the term's words appear in the item's shown text. This is deliberately
 * simple and honest: it is why-this-matched by literal overlap, so a first-time
 * visitor with no terms sees NO cards (the product watches for one person, it does
 * not hand everyone the same feed). */
function itemMatchesTerm(item, term) {
  const hay = ((item.heading && (item.heading.en + " " + item.heading.es)) || "").toLocaleLowerCase();
  // Whole-word overlap, not substring: "park" must not match "parking". Words <=2
  // chars and a small stoplist are ignored so common filler doesn't force matches.
  const stop = new Set(["the", "and", "for", "you", "your", "can", "put", "next", "who", "why", "how", "what", "los", "las", "una", "por", "con", "del"]);
  const words = term.toLocaleLowerCase().split(/[^a-z\u00E0-\u00FF0-9]+/).filter((w) => w.length >= 3 && !stop.has(w));
  if (!words.length) return false;
  return words.some((w) => {
    const re = new RegExp("(?:^|[^a-z\u00E0-\u00FF0-9])" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?:[^a-z\u00E0-\u00FF0-9]|$)", "i");
    return re.test(hay);
  });
}
function keywordMatches() {
  if (!watches.length) return [];
  const terms = watches.map((w) => w.text);
  const out = [];
  for (const item of changed) {
    const hits = terms.filter((term) => itemMatchesTerm(item, term));
    if (hits.length) out.push({ item, terms: hits });
  }
  return out;
}

/* ---- live vs keyword mode ----
 * `liveResult` caches the last successful live-matcher answer, keyed to the exact
 * watchlist it was computed for. When it matches the current list, matchedItems()
 * returns the model's matches (with the model's own reasons). Otherwise we fall
 * back to the transparent keyword filter. The page always states which mode it is
 * in (addition 5), never a blank list, never a hanging spinner. */
let liveResult = null; // { key, matches:[{item_id,reason:{en,es},matched_terms}], source }
let watchMode = "keyword"; // "live" | "keyword"

function _watchKey() {
  return watches.map((w) => w.text).join("\u0001");
}

function matchedItems() {
  if (!watches.length) return [];
  if (watchMode === "live" && liveResult && liveResult.key === _watchKey()) {
    // Option A: the live response carries the full card-shaped item WITH each match
    // (m.item), so ANY extracted item renders — not just the two seeded into
    // sample.json. Fall back to the sample join only if a match somehow arrived
    // without its item payload (older Lambda), so we never crash a match to a card.
    const byId = new Map(changed.map((it) => [it.id, it]));
    const out = [];
    for (const m of liveResult.matches) {
      const item = m.item || byId.get(m.item_id);
      if (item) out.push({ item, terms: m.matched_terms || [], liveReason: m.reason });
    }
    return out;
  }
  return keywordMatches();
}

// Same-origin proxy by default (Vercel /api/watch invokes the watcher Lambda; no
// CORS). config.js may override for local testing; "" disables the live path
// (keyword-only). The page always falls back to the keyword filter on any failure.
const WATCHER_URL = (window.PORCHLIGHT_CONFIG && typeof window.PORCHLIGHT_CONFIG.PORCHLIGHT_WATCHER_URL === "string")
  ? window.PORCHLIGHT_CONFIG.PORCHLIGHT_WATCHER_URL
  : "/api/watch";
const LIVE_TIMEOUT_MS = 8000;

/* Call the deployed watcher. Resolves to {ok, matches, source} on a usable answer,
 * or {ok:false, reason} on any failure/timeout/CORS/degraded — the caller then
 * falls back to keyword mode. Never throws. Terms go in the POST BODY only. */
async function callLiveWatcher(terms) {
  if (!WATCHER_URL) return { ok: false, reason: "no_endpoint" };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), LIVE_TIMEOUT_MS);
  try {
    const res = await fetch(WATCHER_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ terms }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return { ok: false, reason: "http_" + res.status };
    const data = await res.json();
    if (data.degraded) return { ok: false, reason: data.reason || "degraded" };
    // `window` is the corpus window the engine actually searched, read from the DB
    // in the same request (earliest/latest meeting_date + doc count), or absent.
    return { ok: true, matches: data.matches || [], source: data.source || "aurora", window: data.window || null };
  } catch (err) {
    clearTimeout(timer);
    return { ok: false, reason: "network_or_cors" };
  }
}

/* ---- changed cards (real items from sample.json) ---- */
function createChangeCard(match) {
  const item = match.item;
  const matchedTerms = match.terms;
  const liveReason = match.liveReason;  // the model's own reason, when live mode
  const card = document.createElement("article");
  card.className = "change-card " + (item.deadline_actionable ? "hot" : "calm");
  card.lang = language;

  // Status chip: shape + word + colour (survives greyscale).
  const statusRow = document.createElement("div");
  statusRow.className = "change-status";
  const chip = document.createElement("span");
  chip.className = "status-chip";
  const mark = document.createElement("span");
  mark.className = "status-mark " + (item.mark === "off" ? "off" : "added");
  mark.setAttribute("aria-hidden", "true");
  const chipText = document.createElement("span");
  chipText.textContent = item.status ? item.status[language] : "";
  chip.append(mark, chipText);
  const official = document.createElement("span");
  official.className = "official-term";
  official.textContent = item.official_term ? item.official_term[language] : "";
  statusRow.append(chip, official);

  // The shown summary (verified rewrite or honest fallback text) is BODY TEXT —
  // the product's main output, a paragraph, not a display heading. Set as <p> with
  // the .change-summary body style, not <h2> (which is the mock's short-string
  // pull-quote treatment and is wrong for a 100-word paragraph).
  const summary = document.createElement("p");
  summary.className = "change-summary";
  summary.textContent = item.heading ? item.heading[language] : "";
  summary.lang = language;

  card.append(statusRow, summary);

  // Fallback note, when the shown text is original staff text (never.md #7).
  if (item.fallback_note && item.fallback_note[language]) {
    const note = document.createElement("p");
    note.className = "change-scale";
    note.textContent = item.fallback_note[language];
    note.lang = language;
    card.appendChild(note);
  }

  // "Why this matched". In LIVE mode this is the model's own bilingual reason
  // (emitted with the match). In keyword mode it names the watch term(s). Every
  // shown card keeps this line (the product never shows a match without its reason).
  if (liveReason && (liveReason.en || liveReason.es)) {
    const m = document.createElement("p");
    m.className = "watch-match";
    m.textContent = liveReason[language] || liveReason.en || liveReason.es;
    m.lang = language;
    card.appendChild(m);
  } else if (matchedTerms && matchedTerms.length) {
    const m = document.createElement("p");
    m.className = "watch-match";
    const quoted = matchedTerms.map((x) => "\u201C" + x + "\u201D").join(", ");
    m.textContent = (language === "es")
      ? "Usted est\u00E1 siguiendo: " + quoted + "."
      : "You're watching: " + quoted + ".";
    m.lang = language;
    card.appendChild(m);
  }

  // Scale note.
  if (item.scale_note && item.scale_note[language]) {
    card.appendChild(copyNodeText("p", "change-scale", item.scale_note[language]));
  }

  // Deadline: only render + amber when actionable; copied from source or absent.
  if (item.deadline && item.deadline[language]) {
    const dl = document.createElement("p");
    dl.className = item.deadline_actionable ? "deadline-line" : "neutral-deadline";
    const shape = document.createElement("span");
    shape.className = "deadline-shape";
    shape.setAttribute("aria-hidden", "true");
    const dtext = document.createElement("span");
    dtext.textContent = item.deadline[language];
    dl.append(shape, dtext);
    card.appendChild(dl);
  }

  // Receipt (mono), copied from record, with jump-to-page link.
  if (item.receipt) {
    const receipt = document.createElement("div");
    receipt.className = "change-receipt";
    receipt.lang = language;
    const line = document.createElement("div");
    line.textContent = item.receipt.line ? item.receipt.line[language] : "";
    receipt.appendChild(line);
    if (item.receipt.source_href) {
      const link = document.createElement("a");
      link.href = item.receipt.source_href;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = item.receipt.source_label ? item.receipt.source_label[language] : item.receipt.source_href;
      link.setAttribute("aria-label", (item.receipt.source_label ? item.receipt.source_label[language] : "") + " \u2014 " + (item.heading ? item.heading[language].slice(0, 60) : ""));
      receipt.appendChild(link);
    }
    card.appendChild(receipt);
  }

  // Draft action (no send anywhere; opens the stance-empty scaffold).
  const action = document.createElement("button");
  action.type = "button";
  action.className = "primary-button card-action";
  action.textContent = t("startComment");
  action.addEventListener("click", () => {
    const opening = scaffoldOpenId !== item.id;
    scaffoldOpenId = opening ? item.id : null;
    if (opening) {
      // Reopen: if a draft was saved for THIS card, restore the person's words into
      // the fields; otherwise start blank. The textareas read commentDraft, so
      // hydrate it before renderChanged builds them.
      const saved = drafts.find((d) => d.item_id === item.id && d.fields);
      commentDraft.position = saved ? (saved.fields.position || "") : "";
      commentDraft.matters = saved ? (saved.fields.matters || "") : "";
      commentDraft.ask = saved ? (saved.fields.ask || "") : "";
    }
    renderChanged();
    // Fix 3: on OPEN, move focus to the scaffold heading (same pattern as the
    // results heading — instant scroll so it lands before focus, preventScroll so
    // focus doesn't fight it). Keyboard users land in the draft, not back on the
    // results heading. On close, no focus move.
    if (opening) {
      const h = document.getElementById("scaffold-title");
      if (h) {
        h.scrollIntoView({ block: "start", behavior: "instant" });
        h.focus({ preventScroll: true });
      }
    }
  });
  card.appendChild(action);

  if (scaffoldOpenId === item.id) {
    card.appendChild(createCommentScaffold(item));
  }
  return card;
}

function copyNodeText(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  n.textContent = text;
  n.lang = language;
  return n;
}

/* ---- comment scaffold: sourced facts filled, stance fields empty, NO send ---- */
function createScaffoldField(id, labelKey, stateKey) {
  const group = document.createElement("div");
  group.className = "field-group";
  const label = copyNode("label", "", labelKey);
  label.htmlFor = id;
  const ta = document.createElement("textarea");
  ta.id = id;
  ta.value = commentDraft[stateKey];
  ta.lang = language;
  ta.addEventListener("input", () => { commentDraft[stateKey] = ta.value; });
  group.append(label, ta);
  return group;
}
function factRow(labelKey, value) {
  const row = document.createElement("div");
  row.append(copyNode("dt", "", labelKey), copyNodeText("dd", "", value));
  return row;
}
function createCommentScaffold(item) {
  const s = document.createElement("section");
  s.className = "scaffold";
  s.setAttribute("role", "region");
  s.setAttribute("aria-label", t("scaffoldRegion"));
  s.lang = language;
  const title = copyNode("h3", "", "scaffoldTitle");
  title.id = "scaffold-title";
  title.tabIndex = -1;
  const intro = copyNode("p", "", "scaffoldIntro");

  const filled = document.createElement("section");
  filled.className = "scaffold-group scaffold-filled";
  const facts = document.createElement("dl");
  facts.className = "fact-list";
  facts.append(
    factRow("factAboutLabel", item.heading ? item.heading[language] : ""),
    factRow("factMeetingLabel", item.receipt ? item.receipt.line[language] : ""),
    factRow("factReceiptLabel", item.receipt ? item.receipt.line[language] : "")
  );
  filled.append(copyNode("h4", "", "filledTitle"), facts);

  const yours = document.createElement("section");
  yours.className = "scaffold-group scaffold-yours";
  yours.append(
    copyNode("h4", "", "yoursTitle"),
    createScaffoldField("draft-position", "positionLabel", "position"),
    createScaffoldField("draft-matters", "mattersLabel", "matters"),
    createScaffoldField("draft-ask", "askLabel", "ask")
  );

  const note = copyNode("p", "scaffold-note", "scaffoldNote");
  const actions = document.createElement("div");
  actions.className = "scaffold-actions";
  const save = copyNode("button", "primary-button", "saveDraft");
  save.type = "button";
  save.addEventListener("click", () => {
    // Save the person's WORDS with the draft (the three stance fields), plus the
    // item id so a reopened draft reattaches to the right card. One saved draft per
    // item id: re-saving updates it in place rather than piling up duplicates.
    const fields = {
      position: commentDraft.position,
      matters: commentDraft.matters,
      ask: commentDraft.ask,
    };
    const entry = {
      item_id: item.id,
      title: { en: item.heading.en.slice(0, 60), es: item.heading.es.slice(0, 60) },
      edited: { en: COPY.en.editedNow, es: COPY.es.editedNow },
      fields,
    };
    const existing = drafts.findIndex((d) => d.item_id === item.id);
    if (existing >= 0) drafts[existing] = entry;
    else drafts.push(entry);
    renderDrafts();
    // Persist; only claim "saved" if the write actually landed (never.md-honest).
    const stored = saveDraftsToStorage();
    setStatus("draft-status", t(stored ? "draftSavedFromChange" : "draftNotStored"));
  });
  const close = copyNode("button", "secondary-button", "closeScaffold");
  close.type = "button";
  close.addEventListener("click", () => { scaffoldOpenId = null; renderChanged(); });
  // Deliberately NO send button here (never.md #4).
  actions.append(save, close);
  s.append(title, intro, filled, yours, note, actions);
  return s;
}

/* ---- render ---- */
function renderChanged() {
  const list = document.getElementById("change-list");
  if (!list) return;
  const matches = matchedItems();
  list.replaceChildren(...matches.map((m) => createChangeCard(m)));
}

/* ---- the three states, driven by the watchlist (never a shared feed) ----
 * 1. no terms      -> onboarding + reading log, ZERO cards.
 * 2. terms, 0 match -> quiet-state ("Nothing new for you this week") + reading log.
 * 3. terms + match  -> the matched change cards, each with its why-matched line.
 */
function deriveAndRenderState(announce) {
  const hasTerms = watches.length > 0;
  const matches = matchedItems();
  const quiet = document.getElementById("quiet-state");
  const changedState = document.getElementById("changed-state");
  const checks = document.getElementById("checks");        // reading log region
  const quietCopy = quiet ? quiet.querySelector(".quiet-copy") : null;
  const onboarding = quiet ? quiet.querySelector(".paper-stack") : null;

  if (hasTerms && matches.length) {
    // State 3: matched cards.
    activeState = "changed";
    quiet.hidden = true;
    changedState.hidden = false;
    if (checks) checks.hidden = true;
    renderChanged();
  } else {
    // States 1 & 2: no cards. The reading log carries the proof either way.
    activeState = "quiet";
    changedState.hidden = true;
    quiet.hidden = false;
    if (checks) checks.hidden = false;
    // The quiet copy differs by whether the reader has said what matters yet:
    // state 1 (no terms) = onboarding headline, state 2 (terms, no match) = quiet.
    setQuietCopyForState(hasTerms);
  }
  // Keep the nav chips honest about which state is showing.
  document.getElementById("state-quiet").setAttribute("aria-current", String(activeState === "quiet"));
  document.getElementById("state-changed").setAttribute("aria-current", String(activeState === "changed"));
  if (announce !== false) {
    setStatus("state-status", activeState === "changed" ? t("changedStateLoaded") : t("quietStateLoaded"));
  }
}

/* After a submit: put the result where the user is looking, not only in the small
 * status line (A2). On a match, focus the results heading (scrolls it into view)
 * and announce the count via the aria-live region. On no match, set the quiet-state
 * copy to a plain "nothing matches that yet" naming the term, and focus it. */

/* runWatch: the submit orchestrator. Shows a visible working state (addition 6),
 * tries the live watcher, sets live/keyword mode, renders, announces completion,
 * and shows a mode banner. On ANY live failure it falls back to the keyword filter
 * and says so — never a blank list, never a hanging spinner (addition 5). */
async function runWatch(addedTerm) {
  const terms = watches.map((w) => w.text);
  const busy = WATCHER_URL ? true : false;
  if (busy) {
    setStatus("watch-status", t("checkingLive"));
    setBusy(true);
  }
  let mode = "keyword";
  let source = "keyword";
  if (WATCHER_URL) {
    const r = await callLiveWatcher(terms);
    if (r.ok) {
      liveResult = { key: _watchKey(), matches: r.matches, source: r.source };
      mode = "live";
      source = r.source;
      // Show the window the LIVE engine actually searched (Aurora's), not the
      // sample's. If the response carried none, fall back to the sample window
      // rather than inventing one.
      corpusWindow = formatWindow(r.window) || sampleWindow;
    } else {
      liveResult = null;   // fall back to keyword
      mode = "keyword";
      source = "keyword-fallback";
      // Keyword fallback searches the sample corpus, so name the sample's window.
      corpusWindow = sampleWindow;
    }
  }
  watchMode = mode;
  setBusy(false);
  renderModeBanner(mode, source);
  deriveAndRenderState(false);
  announceResult(addedTerm);
}

function setBusy(on) {
  const btn = document.querySelector("#watch-form button[type=submit]");
  if (btn) { btn.disabled = on; btn.setAttribute("aria-busy", String(on)); }
}

/* The mode banner names which engine answered, both languages (addition 5). */
function renderModeBanner(mode, source) {
  const el = document.getElementById("watch-mode");
  if (!el) return;
  let key;
  if (mode === "live") key = "modeLive";
  else if (source === "keyword-fallback") key = "modeFallback";
  else key = "modeKeyword";
  el.textContent = t(key);
  el.lang = language;
  el.hidden = false;
}

function announceResult(term) {
  const matches = matchedItems();
  const status = document.getElementById("state-status");   // aria-live=polite
  if (matches.length) {
    // Bug 3: the VISIBLE watch-status line carries the count (not just the near-top
    // aria-live region). Restores "Watch added. N match(es)."
    const n = matches.length;
    const countMsg = n === 1 ? t("matchCountOne") : t("matchCountMany").replace("{n}", String(n));
    setStatus("watch-status", t("added") + " " + countMsg);
    // aria-live announcement (existing region, not a new one).
    if (status) { status.textContent = countMsg; status.lang = language; }
    // Bug 4 (match case): focus the results heading. Scroll it to the TOP of the
    // viewport unconditionally so the heading LEADS the view (not pinned to the
    // bottom edge); focus with preventScroll so it doesn't override that scroll.
    const heading = document.getElementById("changed-title");
    if (heading) {
      // behavior:"instant", not "smooth" or "auto": a smooth scroll is still in flight
      // when focus() fires on the next line and gets cancelled (preventScroll stops
      // focus from scrolling, it does not stop it aborting a scroll already running).
      // "auto" resolves to the element's CSS scroll-behavior, which is smooth here, so
      // only "instant" forces a synchronous jump that lands before focus().
      heading.scrollIntoView({ block: "start", behavior: "instant" });
      heading.focus({ preventScroll: true });
    }
  } else {
    // Zero-match (Amendment 3): honest empty state at the quiet region, naming the
    // term. deriveAndRenderState already hid the cards and showed the quiet panel,
    // so no stale results remain and it is never a blank panel.
    const titleEl = document.getElementById("quiet-title");
    const bodyEl = titleEl ? titleEl.parentElement.querySelector("p") : null;
    if (titleEl) {
      titleEl.textContent = t("noMatchTitle");
      titleEl.lang = language;
      titleEl.setAttribute("tabindex", "-1");
    }
    if (bodyEl) {
      bodyEl.textContent = t("noMatchBody").replace("{term}", term);
      bodyEl.lang = language;
    }
    // Zero-match: show the corpus window we hold + the Notify Me pointer.
    renderQuietExtras(true);
    // Bug 3 (zero case): the visible line says so too.
    setStatus("watch-status", t("added") + " " + t("noMatchTitle"));
    if (status) { status.textContent = t("noMatchTitle"); status.lang = language; }
    // Bug 4 (zero-match case): focus the quiet-state heading, defined behavior.
    if (titleEl) { titleEl.scrollIntoView({ block: "start", behavior: "instant" }); titleEl.focus({ preventScroll: true }); }
  }
}

/* Rebuild the quiet-copy extras: the corpus-window note (when a window is known)
 * and, in the zero-match case, the Notify Me pointer. Built fresh each call with
 * createElement/textContent (no innerHTML, never.md #12). `showNotify` is true only
 * on a zero-match result, so the "we don't notify, the city does" line lands where a
 * resident just searched and found nothing. */
function renderQuietExtras(showNotify) {
  const quietCopy = document.querySelector("#quiet-state .quiet-copy");
  if (!quietCopy) return;
  const old = quietCopy.querySelector(".state-copy-extra");
  if (old) old.remove();
  const extra = document.createElement("div");
  extra.className = "state-copy-extra";

  // Window note — only when a window is available; never guess one.
  if (corpusWindow && corpusWindow[language]) {
    const win = document.createElement("p");
    win.className = "window-note";
    win.textContent = t("windowNote").replace("{window}", corpusWindow[language]);
    win.lang = language;
    extra.appendChild(win);
  }

  // Notify Me pointer (zero-match only): one sentence + a real link to the city's
  // own notification service. Porch Light sends nothing; the city does.
  if (showNotify) {
    const note = document.createElement("p");
    note.className = "notify-note";
    note.textContent = t("notifyNote");
    note.lang = language;
    const link = document.createElement("a");
    link.href = CITY_NOTIFY_URL;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = t("notifyLink");
    link.lang = language;
    note.append(" ", link);
    extra.appendChild(note);
  }

  if (extra.childNodes.length) quietCopy.appendChild(extra);
}

/* The site footer: four honest lines on EVERY state, both languages. Rendered into
 * #site-footer (a landmark present in all states), rebuilt on language change.
 * createElement/textContent only; the Agenda Center line carries a real link. */
function renderSiteFooter() {
  const footer = document.getElementById("site-footer");
  if (!footer) return;
  footer.replaceChildren();
  footer.lang = language;

  const mk = (key) => {
    const p = document.createElement("p");
    p.textContent = t(key);
    p.lang = language;
    return p;
  };
  footer.appendChild(mk("footerProto"));
  footer.appendChild(mk("footerRunning"));

  const src = document.createElement("p");
  src.textContent = t("footerSource") + " ";
  src.lang = language;
  const link = document.createElement("a");
  link.href = CITY_AGENDA_URL;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = t("footerSourceLink");
  link.lang = language;
  src.appendChild(link);
  footer.appendChild(src);

  footer.appendChild(mk("footerRewrites"));
}

function setQuietCopyForState(hasTerms) {
  const titleEl = document.getElementById("quiet-title");
  const bodyEl = titleEl ? titleEl.parentElement.querySelector("p") : null;
  if (!titleEl) return;
  if (hasTerms) {
    titleEl.textContent = t("quietTitle");          // "Nothing new for you this week."
    if (bodyEl) bodyEl.textContent = t("quietBody");
  } else {
    titleEl.textContent = t("onboardTitle");
    if (bodyEl) bodyEl.textContent = t("onboardBody");
  }
  titleEl.lang = language;
  if (bodyEl) bodyEl.lang = language;
  // Window note on the quiet/onboard states; no Notify Me here (not a zero-match).
  renderQuietExtras(false);
}
function renderWatches() {
  const list = document.getElementById("watch-list");
  const nodes = watches.map((watch, index) => {
    const li = document.createElement("li");
    li.className = "watch-item";
    const text = document.createElement("span");
    text.textContent = watch.text;
    text.lang = watch.lang || language;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-watch";
    remove.textContent = "\u00D7";
    remove.setAttribute("aria-label", t("remove") + ": " + watch.text);
    remove.addEventListener("click", () => { watches.splice(index, 1); saveWatchesToStorage(); renderWatches(); deriveAndRenderState(); });
    li.append(text, remove);
    return li;
  });
  list.replaceChildren(...nodes);
  // The onboarding panel was removed (the example chips do that job); the
  // "Currently watching" label only shows once there is at least one watch.
  const savedTitle = document.getElementById("saved-title");
  if (savedTitle) savedTitle.hidden = watches.length === 0;
}
function renderDrafts() {
  const nodes = drafts.map((draft) => {
    const li = document.createElement("li");
    li.className = "draft-item";
    li.lang = language;
    const icon = document.createElement("span");
    icon.className = "doc-icon";
    icon.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.textContent = draft.title[language];
    const edited = document.createElement("small");
    edited.textContent = draft.edited[language];
    text.appendChild(edited);
    li.append(icon, text);
    return li;
  });
  document.getElementById("draft-list").replaceChildren(...nodes);
}
function renderChecks() {
  const list = document.getElementById("check-list");
  if (!list) return;
  const nodes = t("historyLines").map((lineText) => {
    const li = document.createElement("li");
    li.className = "check-row";
    li.lang = language;
    const shape = document.createElement("span");
    shape.className = "status-shape neutral";
    shape.setAttribute("aria-hidden", "true");
    const detail = document.createElement("div");
    detail.className = "check-detail";
    detail.textContent = lineText;
    li.append(shape, detail);
    return li;
  });
  list.replaceChildren(...nodes);
}

function setMainState(next, announce) {
  // State is derived from the watchlist, never forced to a shared feed. The nav
  // buttons re-derive; they cannot manufacture change cards the reader didn't earn
  // with a watch term (that was the new-user bug). announce carries through.
  deriveAndRenderState(announce);
}

function setLanguage(next) {
  language = next;
  document.documentElement.lang = language;
  document.getElementById("lang-en").setAttribute("aria-pressed", String(language === "en"));
  document.getElementById("lang-es").setAttribute("aria-pressed", String(language === "es"));
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (COPY[language][key]) { node.textContent = COPY[language][key]; node.lang = language; }
  });
  document.querySelectorAll("[data-aria-i18n]").forEach((node) => {
    const key = node.getAttribute("data-aria-i18n");
    if (COPY[language][key]) node.setAttribute("aria-label", COPY[language][key]);
  });
  document.querySelectorAll("[data-placeholder-i18n]").forEach((node) => {
    const key = node.getAttribute("data-placeholder-i18n");
    if (COPY[language][key]) node.placeholder = COPY[language][key];
  });
  const toggle = document.getElementById("history-toggle");
  const expanded = toggle.getAttribute("aria-expanded") === "true";
  toggle.textContent = expanded ? t("historyClose") : t("history");
  renderChecks(); renderWatches(); renderDrafts(); renderSiteFooter();
  deriveAndRenderState(false);   // re-render cards/quiet/onboard in the new language
  setStatus("watch-status", ""); setStatus("draft-status", "");
}

/* ---- shared-link confirm (shown, never auto-applied) ---- */
function offerSharedList(terms) {
  const host = document.getElementById("watch-status");
  const wrap = document.createElement("span");
  const msg = document.createElement("span");
  msg.textContent = t("shareConfirm");
  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "text-link";
  apply.textContent = t("shareApply");
  apply.style.marginInline = "0.5rem";
  apply.addEventListener("click", () => {
    watches = terms.slice(0, MAX_TERMS).map((text) => ({ text, lang: language }));
    saveWatchesToStorage();
    renderWatches();
    deriveAndRenderState();
    setStatus("watch-status", t("shareApplied"));
  });
  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.className = "text-link";
  dismiss.textContent = t("shareDismiss");
  dismiss.addEventListener("click", () => { syncFragment(); setStatus("watch-status", t("shareDismissed")); });
  wrap.append(msg, apply, dismiss);
  host.replaceChildren(wrap);
  host.lang = language;
}

/* ---- live character counter (mirrors the server cap; no amber, voice.md) ---- */
function updateCharCount() {
  const input = document.getElementById("watch-input");
  const num = document.getElementById("watch-count-num");
  const wrap = document.getElementById("watch-count");
  if (!input || !num || !wrap) return;
  const n = input.value.length;
  num.textContent = String(n);
  wrap.classList.toggle("over", n >= MAX_TERM_CHARS);
}

/* ---- events ---- */
function wireEvents() {
  const watchInput = document.getElementById("watch-input");
  if (watchInput) watchInput.addEventListener("input", updateCharCount);
  // Example chips fill the input so a first-time user sees both a question and a
  // phrase are valid, then can edit from there.
  document.querySelectorAll(".example-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const input = document.getElementById("watch-input");
      if (!input) return;
      // Strip the surrounding smart quotes from the chip label.
      input.value = chip.textContent.replace(/^[\u201C"]|[\u201D"]$/g, "").trim();
      updateCharCount();
      input.focus();
    });
  });

  document.getElementById("watch-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("watch-input");
    const value = normalizeTerm(input.value);
    const err = validateNewTerm(value);
    if (err) { setStatus("watch-status", t(err)); input.focus(); return; }
    watches.push({ text: value, lang: language });
    input.value = "";
    updateCharCount();
    saveWatchesToStorage();
    renderWatches();
    runWatch(value);   // async: loading -> live call (fallback to keyword) -> announce
  });
  document.getElementById("history-toggle").addEventListener("click", (event) => {
    const button = event.currentTarget;
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    document.getElementById("history-extra").hidden = expanded;
    button.textContent = expanded ? t("history") : t("historyClose");
  });
  document.getElementById("start-draft").addEventListener("click", () => {
    drafts.push({
      title: { en: COPY.en.untitledDraft, es: COPY.es.untitledDraft },
      edited: { en: COPY.en.editedNow, es: COPY.es.editedNow }
    });
    renderDrafts();
    const stored = saveDraftsToStorage();
    setStatus("draft-status", t(stored ? "draftAdded" : "draftNotStored"));
  });
  document.getElementById("lang-en").addEventListener("click", () => setLanguage("en"));
  document.getElementById("lang-es").addEventListener("click", () => setLanguage("es"));
  document.getElementById("state-quiet").addEventListener("click", () => deriveAndRenderState());
  document.getElementById("state-changed").addEventListener("click", () => deriveAndRenderState());

  // Clear-everything: confirm, then wipe watchlist + drafts + URL fragment +
  // localStorage back to the true new-user state (addition 8). A privacy-first
  // product must let a person clear their own data without opening devtools.
  const clearBtn = document.getElementById("clear-all");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const host = document.getElementById("clear-status");
      const wrap = document.createElement("span");
      wrap.className = "clear-confirm";
      const msg = document.createElement("span");
      msg.textContent = t("clearConfirm"); msg.lang = language;
      const yes = document.createElement("button");
      yes.type = "button"; yes.className = "text-link"; yes.textContent = t("clearYes"); yes.lang = language;
      yes.addEventListener("click", clearEverything);
      const no = document.createElement("button");
      no.type = "button"; no.className = "text-link"; no.textContent = t("clearNo"); no.lang = language;
      no.addEventListener("click", () => { host.replaceChildren(); });
      wrap.append(msg, yes, no);
      host.replaceChildren(wrap);
    });
  }
}

function clearEverything() {
  watches = [];
  drafts = [];
  liveResult = null;
  watchMode = "keyword";
  commentDraft.position = commentDraft.matters = commentDraft.ask = "";
  try { localStorage.removeItem(WATCH_KEY); } catch (e) { /* storage may be blocked */ }
  try { localStorage.removeItem(DRAFTS_KEY); } catch (e) { /* storage may be blocked */ }
  // Wipe the URL fragment (shared terms) without reloading.
  history.replaceState(null, "", location.pathname + location.search);
  const modeEl = document.getElementById("watch-mode");
  if (modeEl) modeEl.hidden = true;
  renderWatches();
  renderDrafts();
  deriveAndRenderState(false);   // -> true new-user onboarding state
  setStatus("clear-status", t("cleared"));
}

/* ---- boot ---- */
async function loadChanged() {
  try {
    const res = await fetch("sample.json", { cache: "no-store" });
    if (!res.ok) throw new Error("http " + res.status);
    const view = await res.json();
    changed = Array.isArray(view.changed) ? view.changed : [];
    // The sample's own window field (data, not parsed from receipts). Used on the
    // keyword-fallback path and as the initial window before any live call.
    sampleWindow = formatWindow(view.window);
    corpusWindow = sampleWindow;
  } catch (err) {
    // Honest empty state, never a blank screen (security.md).
    changed = [];
    setStatus("state-status", "The city record could not be loaded right now.");
  }
}

async function boot() {
  wireEvents();
  // Watchlist: an incoming shared link is shown-and-confirmed; otherwise localStorage.
  const shared = parseFragmentTerms();
  watches = loadWatchesFromStorage();
  drafts = loadDraftsFromStorage();   // per-device, never server-side
  await loadChanged();
  setLanguage("en");
  updateCharCount();
  renderWatches();
  renderDrafts();                // show any drafts restored from localStorage
  deriveAndRenderState(false);   // new user (no terms) -> onboarding + reading log, ZERO cards
  if (shared && shared.length) offerSharedList(shared);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
