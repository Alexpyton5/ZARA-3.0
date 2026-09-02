import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

declare const d3: any;

type MemoryNode = { id: string; title?: string; kind?: string; r?: number; group?: string };
type MemoryLink = { source: string; target: string };
type ChatMessage = { role?: string; content?: string; message?: string };

const $ = <T extends Element>(selector: string) => document.querySelector<T>(selector);
const $$ = <T extends Element>(selector: string) => [...document.querySelectorAll<T>(selector)];
const fallbackNodes: MemoryNode[] = [
  { id: "ZARA", title: "ZARA", group: "core", r: 16 },
  { id: "Alex", title: "Alex", group: "core", r: 11 },
  { id: "Projeto", title: "Projeto", group: "memory", r: 9 },
  { id: "Rotina", title: "Rotina", group: "memory", r: 8 },
  { id: "Ideias", title: "Ideias", group: "memory", r: 8 },
  { id: "Claude", title: "Claude", group: "service", r: 8 },
  { id: "Reunião", title: "Reunião", group: "memory", r: 7 },
];
const fallbackLinks: MemoryLink[] = [
  ["ZARA", "Alex"], ["ZARA", "Projeto"], ["ZARA", "Rotina"], ["ZARA", "Claude"],
  ["Alex", "Ideias"], ["Projeto", "Reunião"], ["Ideias", "Claude"],
].map(([source, target]) => ({ source, target }));

let isListening = false;
let simulation: any;
let toastTimer: number | undefined;
let conversation: Array<{ role: string; content: string }> = [];

function showToast(message: string) {
  const toast = $("#toast")!;
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
}

async function requestZara(requestType: string, payload: Record<string, unknown> = {}) {
  return invoke<any>("zara_request", { requestType, payload });
}

function responseText(response: any): string {
  const value = response?.content ?? response?.response ?? response?.message ?? response?.result?.message;
  return typeof value === "string" ? value.trim() : "";
}

function setConnection(online: boolean) {
  const indicator = $("#connection-state")!;
  indicator.classList.toggle("online", online);
  indicator.lastChild!.textContent = online ? " conectada" : " indisponível";
}

function addMessage(text: string, fromUser = false) {
  const messages = $("#messages")!;
  const article = document.createElement("article");
  article.className = `message ${fromUser ? "user-message" : "zara-message"}`;
  const marker = document.createElement("span");
  marker.className = "message-avatar";
  marker.textContent = fromUser ? "A" : "Z";
  const body = document.createElement("p");
  body.textContent = text;
  article.append(marker, body);
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
}

function renderConversation(messages: ChatMessage[]) {
  const target = $("#messages")!;
  target.replaceChildren();
  const valid = messages.filter((message) => typeof (message.content ?? message.message) === "string");
  if (!valid.length) {
    addMessage("Olá, Alex. Estou aqui.");
    return;
  }
  valid.slice(-40).forEach((message) => addMessage(String(message.content ?? message.message), message.role === "user"));
}

async function loadConversationHistory() {
  try {
    const response = await requestZara("conversation-history-list", { limit: 40 });
    if (!Array.isArray(response?.messages)) throw new Error("Histórico indisponível.");
    renderConversation(response.messages);
    setConnection(true);
  } catch {
    setConnection(false);
  }
}

async function submitMessage(text: string) {
  const value = text.trim();
  if (!value) return;
  addMessage(value, true);
  conversation = [...conversation, { role: "user", content: value }].slice(-16);
  try {
    const response = await requestZara("send-message", { message: value, engine: "auto", history: conversation });
    const reply = responseText(response);
    if (!reply) throw new Error("A ZARA respondeu sem texto para mostrar.");
    addMessage(reply);
    conversation = [...conversation, { role: "assistant", content: reply }].slice(-16);
    setConnection(true);
  } catch (error) {
    setConnection(false);
    addMessage(error instanceof Error ? error.message : "Não consegui falar com a ZARA agora.");
  }
}

function setVoiceVisualState(listening: boolean) {
  isListening = listening;
  const voiceButton = $("#voice-toggle")!;
  voiceButton.textContent = listening ? "● Ouvindo" : "♩ Microfone";
  voiceButton.classList.toggle("is-listening", listening);
  voiceButton.setAttribute("aria-pressed", String(listening));
}

async function toggleVoice() {
  const target = !isListening;
  try {
    const response = await requestZara(target ? "voice-start" : "voice-stop");
    if (response?.success === false) throw new Error(responseText(response) || "A ZARA não confirmou a mudança de escuta.");
    setVoiceVisualState(target);
    setConnection(true);
    showToast(target ? "A ZARA confirmou que começou a ouvir." : "A ZARA confirmou que parou de ouvir.");
  } catch (error) {
    setConnection(false);
    showToast(error instanceof Error ? error.message : "Não consegui mudar a escuta agora.");
  }
}

function updateClock() {
  const now = new Date();
  $("#clock")!.textContent = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(now);
  $("#date-label")!.textContent = new Intl.DateTimeFormat("pt-BR", { weekday: "short", day: "numeric", month: "short" }).format(now).replace(".", "");
}

function renderMemoryGraph(nodes = fallbackNodes, links = fallbackLinks) {
  const container = $("#memory-graph")!;
  if (typeof d3 === "undefined") {
    $("#memory-count")!.textContent = "O visual do grafo não pôde ser carregado.";
    return;
  }
  simulation?.stop();
  container.replaceChildren();
  const width = Math.max(container.clientWidth, 300);
  const height = Math.max(container.clientHeight, 180);
  const graphNodes = nodes.slice(0, 36).map((node, index) => ({ ...node, id: String(node.id), label: String(node.title || node.id), r: node.r ?? (index === 0 ? 16 : 8) }));
  const identifiers = new Set(graphNodes.map((node) => node.id));
  const graphLinks = links.filter((link) => identifiers.has(String(link.source)) && identifiers.has(String(link.target)));
  const svg = d3.select(container).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
  const defs = svg.append("defs");
  const gradient = defs.append("radialGradient").attr("id", "crystal-gradient");
  gradient.append("stop").attr("offset", "0%").attr("stop-color", "#ffffff").attr("stop-opacity", .96);
  gradient.append("stop").attr("offset", "42%").attr("stop-color", "#d4f0ff").attr("stop-opacity", .78);
  gradient.append("stop").attr("offset", "100%").attr("stop-color", "#c8b6ff").attr("stop-opacity", .48);
  const graph = svg.append("g");
  svg.call(d3.zoom().scaleExtent([.7, 2.5]).on("zoom", (event: any) => graph.attr("transform", event.transform)));
  const link = graph.append("g").selectAll("line").data(graphLinks).join("line").attr("class", "memory-link");
  const node = graph.append("g").selectAll("g").data(graphNodes).join("g").attr("class", "memory-node");
  node.append("circle").attr("class", "memory-node-crystal").attr("r", (d: any) => d.r);
  node.append("circle").attr("class", "memory-node-core").attr("r", (d: any) => Math.max(2.6, d.r * .29));
  const tag = node.append("g").attr("transform", (d: any) => `translate(0,${d.r + 13})`);
  tag.append("rect").attr("class", "memory-node-tag").attr("x", (d: any) => -Math.max(28, d.label.length * 3.85 + 11)).attr("y", -10).attr("width", (d: any) => Math.max(56, d.label.length * 7.7 + 22)).attr("height", 21).attr("rx", 10.5);
  tag.append("text").attr("class", "memory-node-text").attr("text-anchor", "middle").attr("dy", 4).text((d: any) => d.label.length > 18 ? `${d.label.slice(0, 17)}…` : d.label);
  simulation = d3.forceSimulation(graphNodes).force("link", d3.forceLink(graphLinks).id((d: any) => d.id).distance(96).strength(.6)).force("charge", d3.forceManyBody().strength(-230)).force("center", d3.forceCenter(width / 2, height / 2)).force("collide", d3.forceCollide((d: any) => d.r + 50)).on("tick", () => {
    link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y).attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
    node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
  });
  node.call(d3.drag().on("start", (event: any, d: any) => { if (!event.active) simulation.alphaTarget(.3).restart(); d.fx = d.x; d.fy = d.y; }).on("drag", (event: any, d: any) => { d.fx = event.x; d.fy = event.y; }).on("end", (event: any, d: any) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));
}

async function loadRealMemory() {
  const caption = $("#memory-count")!;
  try {
    const response = await requestZara("memory-galaxy-list");
    if (response?.success === false || !Array.isArray(response?.nodes)) throw new Error("Memórias indisponíveis.");
    const nodes = response.nodes as MemoryNode[];
    const links = Array.isArray(response.links) ? response.links as MemoryLink[] : [];
    renderMemoryGraph(nodes.length ? nodes : fallbackNodes, links.length ? links : fallbackLinks);
    caption.textContent = nodes.length ? `${nodes.length} memórias reais` : "Sem memória real disponível";
    caption.parentElement!.classList.toggle("online", nodes.length > 0);
    setConnection(true);
  } catch {
    renderMemoryGraph();
    caption.textContent = "Visualização local — ponte indisponível";
    caption.parentElement!.classList.remove("online");
    setConnection(false);
  }
}

function writeTerminal(lines: Array<{ text: string; muted?: boolean }>) {
  const target = $("#terminal-lines")!;
  target.replaceChildren(...lines.map(({ text, muted }) => {
    const line = document.createElement("p");
    line.className = muted ? "terminal-muted" : "terminal-ok";
    line.textContent = text;
    return line;
  }));
}

async function refreshBridgeStatus() {
  writeTerminal([{ text: "› verificando a ponte ZARA...", muted: true }]);
  try {
    const status = await requestZara("voice-status");
    if (status?.success === false) throw new Error(responseText(status) || "Ponte indisponível.");
    const live = status?.gemini_live;
    const mode = live?.connected ? "Gemini Live conectado" : "Motor respondeu; voz não conectada";
    writeTerminal([{ text: "✓ ponte ZARA respondeu" }, { text: `› ${mode}`, muted: true }, { text: `› estado: ${status?.pipeline_state ?? "não informado"}`, muted: true }]);
    setVoiceVisualState(Boolean(status?.listening));
    setConnection(true);
  } catch (error) {
    writeTerminal([{ text: "Ponte não confirmou conexão.", muted: true }, { text: error instanceof Error ? error.message : "Erro desconhecido.", muted: true }]);
    setConnection(false);
  }
}

async function minimizeWindow() {
  try { await getCurrentWindow().minimize(); } catch { showToast("Minimizar só funciona dentro do aplicativo ZARA."); }
}

async function closeWindow() {
  try { await getCurrentWindow().close(); } catch { showToast("Fechar só funciona dentro do aplicativo ZARA."); }
}

function bindInteractions() {
  $("#composer")!.addEventListener("submit", (event) => { event.preventDefault(); const input = $("#message-input") as HTMLInputElement; void submitMessage(input.value); input.value = ""; });
  $("#voice-toggle")!.addEventListener("click", () => void toggleVoice());
  $("#refresh-history")!.addEventListener("click", () => void loadConversationHistory());
  $("#graph-reset")?.addEventListener("click", () => { simulation?.alpha(1).restart(); });
  $("#terminal-refresh")!.addEventListener("click", () => void refreshBridgeStatus());
  $("#btn-min")?.addEventListener("click", () => void minimizeWindow());
  $("#btn-close")?.addEventListener("click", () => void closeWindow());
  $$<HTMLButtonElement>("[data-room]").forEach((button) => button.addEventListener("click", () => showToast("O Telegram ainda não está conectado nesta versão.")));
  $$<HTMLButtonElement>("[data-dock]").forEach((button) => button.addEventListener("click", () => {
    const action = button.dataset.dock;
    if (action === "voice") void toggleVoice();
    if (action === "memory") simulation?.alpha(1).restart();
    if (action === "refresh") void loadRealMemory();
    if (action === "status") void refreshBridgeStatus();
    if (action === "minimize") void minimizeWindow();
    if (action === "close") void closeWindow();
  }));
}

window.addEventListener("DOMContentLoaded", () => {
  updateClock();
  window.setInterval(updateClock, 1000);
  bindInteractions();
  window.requestAnimationFrame(() => { renderMemoryGraph(); void loadRealMemory(); void loadConversationHistory(); });
});
