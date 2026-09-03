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
const commentDraft = { position: "", matters: "", ask: "" };
let commentDraftSaved = false;
let scaffoldOpenId = null; // which card's scaffold is open, if any

const WATCH_KEY = "porchlight.watches.v1";
const MAX_TERMS = 10;
const MAX_TERM_CHARS = 60;

/* ---- copy (bilingual, verbatim strings load-bearing) ---- */
const COPY = {
  en: {
    skip: "Skip to main content", navLabel: "Primary navigation", languageLabel: "Language",
    navQuiet: "Quiet week", navChanges: "Changed", navCalendar: "Calendar", navBodies: "All bodies", navHow: "How it works",
    navUnavailable: "(not available in this preview)",
    sample: "Real City of Ventura agenda items, read and verified by Porch Light.",
    greeting: "Good afternoon, neighbor.", heartbeatTitle: "System heartbeat",
    cityRead: "City read from stored agendas", readCount: "2 meetings read", nextCheck: "Next check: hourly, on schedule",
    quietTitle: "Nothing new for you this week.",
    quietBody: "We read the City Council and Planning Commission agendas. Add a watch above, or open Changed to see what landed.",
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
    recentChecks: "Recent checks", checksRegion: "Recent checks and source status",
    history: "See full check history", historyClose: "Hide full check history",
    historyLines: ["Hourly checks run on schedule.", "Change detection has fired on a real changed document."],
    packetHeading: "The last thing we read", sourceLabel: "Original source document as published by the city.", packetSummary: "Open the source document",
    toolsRegion: "Your drafts and writing tools", watchRegion: "Start and manage watches",
    watchKicker: "Start here", watchTitle: "Tell Porch Light what matters.",
    watchIntro: "Describe a project, place, concern, or question in your own words. Porch Light checks the public record and brings back relevant changes.",
    watchLabel: "What should Porch Light watch for?", watchPlaceholder: "Can they put a bar next to my house?",
    startWatching: "Start watching", helper: "Use your own words. Porch Light keeps checking.", saved: "Currently watching",
    firstRunTitle: "Start with one thing you care about.",
    firstRunBody: "A watch is a phrase Porch Light checks against new agenda items. For example: \u201cstreet trees on Juniper Avenue.\u201d Type your own words above.",
    privacy: "Your list stays on your device. We use it to answer, and never store it.",
    draftTitle: "Drafts are yours to finish and send.",
    draftExplainer: "Porch Light fills in the facts and the deadline from the source. The opinion is yours to write, and only you can send it.",
    startDraft: "\uFF0B Start a draft",
    remove: "Remove watch", added: "Watch added.", empty: "Enter something you want Porch Light to watch.",
    tooLong: "That watch is too long (max 60 characters).", tooMany: "You can watch up to 10 things.", duplicate: "You're already watching that.",
    draftAdded: "A blank draft was added.", untitledDraft: "Untitled public comment", editedNow: "Edited now",
    shareConfirm: "A shared list was found in this link. Apply it? This replaces your current list.",
    shareApply: "Apply shared list", shareDismiss: "Keep my list", shareApplied: "Shared list applied.", shareDismissed: "Kept your list.",
    aboutTitle: "What this is",
    aboutBody: "Porch Light reads the public agenda packets your city posts, breaks them into individual items, and watches for the things you care about. Every summary points back to the page it came from. It drafts. You write your position, and you decide whether to send it.",
    limitsTitle: "What it does not do",
    limitOne: "It never scores, grades, or ranks a public body.",
    limitTwo: "It never sends anything to a government office. There is no send button anywhere in the code.",
    limitThree: "It never generates a date, a deadline, an item number, or a page range. Those are copied from the source or not shown.",
    limitFour: "It never stores your watch list. That list lives on your device.",
    disclaimerTitle: "Independent project",
    disclaimer: "Porch Light is an independent project. It is not affiliated with, endorsed by, or operated by any city or public agency. Always confirm dates and deadlines against the city's own posting.",
    builtTitle: "Built by", built: "Built by Shara Cordero. AI assisted. Human approved. Powered by NLP.",
    linksTitle: "Links", linkedinPending: "LinkedIn \u00B7 URL to be supplied", sourcePending: "Source code \u00B7 URL to be supplied",
    cityAgenda: "The city's own agenda page"
  },
  es: {
    skip: "Saltar al contenido principal", navLabel: "Navegaci\u00F3n principal", languageLabel: "Idioma",
    navQuiet: "Semana tranquila", navChanges: "Cambios", navCalendar: "Calendario", navBodies: "Todos los organismos", navHow: "C\u00F3mo funciona",
    navUnavailable: "(no disponible en esta vista previa)",
    sample: "Puntos reales de la agenda de la Ciudad de Ventura, le\u00EDdos y verificados por Porch Light.",
    greeting: "Buenas tardes, vecindad.", heartbeatTitle: "Estado del sistema",
    cityRead: "Ciudad le\u00EDda de agendas almacenadas", readCount: "2 reuniones le\u00EDdas", nextCheck: "Pr\u00F3xima revisi\u00F3n: cada hora, seg\u00FAn lo programado",
    quietTitle: "Nada nuevo para usted esta semana.",
    quietBody: "Le\u00EDmos las agendas del Concejo Municipal y de la Comisi\u00F3n de Planificaci\u00F3n. Agregue un tema arriba o abra Cambios para ver lo que lleg\u00F3.",
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
    recentChecks: "Revisiones recientes", checksRegion: "Revisiones recientes y estado de las fuentes",
    history: "Ver historial completo", historyClose: "Ocultar historial completo",
    historyLines: ["Las revisiones por hora se ejecutan seg\u00FAn lo programado.", "La detecci\u00F3n de cambios se activ\u00F3 en un documento real modificado."],
    packetHeading: "Lo \u00FAltimo que le\u00EDmos", sourceLabel: "Documento fuente original tal como lo public\u00F3 la ciudad.", packetSummary: "Abrir el documento fuente",
    toolsRegion: "Sus borradores y herramientas de escritura", watchRegion: "Iniciar y administrar temas de seguimiento",
    watchKicker: "Empiece aqu\u00ED", watchTitle: "D\u00EDgale a Porch Light lo que le importa.",
    watchIntro: "Describa un proyecto, lugar, inquietud o pregunta con sus propias palabras. Porch Light revisa el registro p\u00FAblico y le presenta los cambios pertinentes.",
    watchLabel: "\u00BFQu\u00E9 debe vigilar Porch Light?", watchPlaceholder: "\u00BFPueden poner un bar al lado de mi casa?",
    startWatching: "Empezar a vigilar", helper: "Use sus propias palabras. Porch Light sigue revisando.", saved: "En seguimiento",
    firstRunTitle: "Empiece con algo que le importe.",
    firstRunBody: "Un tema es una frase que Porch Light compara con nuevos asuntos de las agendas. Por ejemplo: \u201c\u00E1rboles en la avenida Juniper\u201D. Escriba sus propias palabras arriba.",
    privacy: "Su lista permanece en su dispositivo. La usamos para responderle y nunca la guardamos.",
    draftTitle: "Usted termina y env\u00EDa sus borradores.",
    draftExplainer: "Porch Light completa los hechos y el plazo a partir de la fuente. La opini\u00F3n la escribe usted y solamente usted puede enviarla.",
    startDraft: "\uFF0B Iniciar un borrador",
    remove: "Eliminar tema", added: "Tema agregado.", empty: "Escriba algo que desea que Porch Light vigile.",
    tooLong: "Ese tema es demasiado largo (m\u00E1ximo 60 caracteres).", tooMany: "Puede vigilar hasta 10 cosas.", duplicate: "Ya est\u00E1 vigilando eso.",
    draftAdded: "Se agreg\u00F3 un borrador en blanco.", untitledDraft: "Comentario p\u00FAblico sin t\u00EDtulo", editedNow: "Editado ahora",
    shareConfirm: "Se encontr\u00F3 una lista compartida en este enlace. \u00BFAplicarla? Esto reemplaza su lista actual.",
    shareApply: "Aplicar lista compartida", shareDismiss: "Conservar mi lista", shareApplied: "Lista compartida aplicada.", shareDismissed: "Conserv\u00F3 su lista.",
    aboutTitle: "Qu\u00E9 es esto",
    aboutBody: "Porch Light lee los paquetes de agendas p\u00FAblicas que publica su ciudad, los divide en asuntos individuales y vigila lo que a usted le importa. Cada resumen remite a la p\u00E1gina de la que proviene. Prepara borradores. Usted escribe su posici\u00F3n y decide si desea enviarla.",
    limitsTitle: "Qu\u00E9 no hace",
    limitOne: "Nunca punt\u00FAa, califica ni clasifica a un organismo p\u00FAblico.",
    limitTwo: "Nunca env\u00EDa nada a una oficina gubernamental. No hay ning\u00FAn bot\u00F3n para enviar en el c\u00F3digo.",
    limitThree: "Nunca genera una fecha, un plazo, un n\u00FAmero de asunto ni un rango de p\u00E1ginas. Esos datos se copian de la fuente o no se muestran.",
    limitFour: "Nunca almacena su lista de temas. Esa lista vive en su dispositivo.",
    disclaimerTitle: "Proyecto independiente",
    disclaimer: "Porch Light es un proyecto independiente. No est\u00E1 afiliado, respaldado ni operado por ninguna ciudad ni organismo p\u00FAblico. Confirme siempre las fechas y los plazos en la publicaci\u00F3n oficial de la ciudad.",
    builtTitle: "Creado por", built: "Creado por Shara Cordero. Con asistencia de IA. Aprobado por una persona. Impulsado por PLN.",
    linksTitle: "Enlaces", linkedinPending: "LinkedIn \u00B7 URL pendiente", sourcePending: "C\u00F3digo fuente \u00B7 URL pendiente",
    cityAgenda: "P\u00E1gina oficial de agendas de la ciudad"
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

/* ---- changed cards (real items from sample.json) ---- */
function createChangeCard(item) {
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

  // Heading = the shown summary (verified rewrite or honest fallback text).
  const heading = document.createElement("h2");
  heading.textContent = item.heading ? item.heading[language] : "";
  heading.lang = language;

  card.append(statusRow, heading);

  // Fallback note, when the shown text is original staff text (never.md #7).
  if (item.fallback_note && item.fallback_note[language]) {
    const note = document.createElement("p");
    note.className = "change-scale";
    note.textContent = item.fallback_note[language];
    note.lang = language;
    card.appendChild(note);
  }

  // Match reason (emitted with the item; on the static page, why it is shown).
  if (item.match_reason && item.match_reason[language]) {
    const match = document.createElement("p");
    match.className = "watch-match";
    match.textContent = item.match_reason[language];
    match.lang = language;
    card.appendChild(match);
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
    scaffoldOpenId = (scaffoldOpenId === item.id) ? null : item.id;
    renderChanged();
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
    drafts.push({
      title: { en: item.heading.en.slice(0, 60), es: item.heading.es.slice(0, 60) },
      edited: { en: COPY.en.editedNow, es: COPY.es.editedNow }
    });
    renderDrafts();
    setStatus("draft-status", t("draftSavedFromChange"));
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
  list.replaceChildren(...changed.map(createChangeCard));
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
    remove.addEventListener("click", () => { watches.splice(index, 1); saveWatchesToStorage(); renderWatches(); });
    li.append(text, remove);
    return li;
  });
  list.replaceChildren(...nodes);
  const empty = watches.length === 0;
  document.getElementById("watch-empty").hidden = !empty;
  document.getElementById("saved-title").hidden = empty;
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
  activeState = next;
  const quiet = document.getElementById("quiet-state");
  const changedState = document.getElementById("changed-state");
  const isChanged = next === "changed";
  quiet.hidden = isChanged;
  changedState.hidden = !isChanged;
  document.getElementById("state-quiet").setAttribute("aria-current", String(!isChanged));
  document.getElementById("state-changed").setAttribute("aria-current", String(isChanged));
  if (announce !== false) setStatus("state-status", isChanged ? t("changedStateLoaded") : t("quietStateLoaded"));
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
  renderChecks(); renderWatches(); renderDrafts(); renderChanged();
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

/* ---- events ---- */
function wireEvents() {
  document.getElementById("watch-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("watch-input");
    const value = normalizeTerm(input.value);
    const err = validateNewTerm(value);
    if (err) { setStatus("watch-status", t(err)); input.focus(); return; }
    watches.push({ text: value, lang: language });
    input.value = "";
    saveWatchesToStorage();
    setStatus("watch-status", t("added"));
    renderWatches();
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
    setStatus("draft-status", t("draftAdded"));
    renderDrafts();
  });
  document.getElementById("lang-en").addEventListener("click", () => setLanguage("en"));
  document.getElementById("lang-es").addEventListener("click", () => setLanguage("es"));
  document.getElementById("state-quiet").addEventListener("click", () => setMainState("quiet"));
  document.getElementById("state-changed").addEventListener("click", () => setMainState("changed"));
}

/* ---- boot ---- */
async function loadChanged() {
  try {
    const res = await fetch("sample.json", { cache: "no-store" });
    if (!res.ok) throw new Error("http " + res.status);
    const view = await res.json();
    changed = Array.isArray(view.changed) ? view.changed : [];
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
  await loadChanged();
  setLanguage("en");
  setMainState("changed", false); // real items exist; show them
  renderWatches();
  if (shared && shared.length) offerSharedList(shared);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
