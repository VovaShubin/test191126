const campaignSelect = document.querySelector("#campaign-select");
const streamsRoot = document.querySelector("#streams");
const toast = document.querySelector("#toast");
let currentCampaign = null;
let offerOptions = [];

function notify(message, error = false) {
  toast.textContent = message;
  toast.className = `show${error ? " error" : ""}`;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { toast.className = ""; }, 3500);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Ошибка HTTP ${response.status}`);
  return data;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

async function loadCampaigns(selectedId = "") {
  const campaigns = await api("/api/campaigns");
  campaignSelect.innerHTML = '<option value="">Выберите кампанию</option>' +
    campaigns.map(item =>
      `<option value="${item.id}" ${String(item.id) === String(selectedId) ? "selected" : ""}>` +
      `#${item.id} — ${escapeHtml(item.name)}</option>`
    ).join("");
}

async function loadOffers() {
  offerOptions = await api("/api/offers");
}

function offerRows(stream) {
  if (!stream.offers.length) {
    return '<tr><td colspan="3" class="muted">В потоке пока нет офферов.</td></tr>';
  }
  return stream.offers.map(offer => `
    <tr class="${offer.removed ? "removed" : ""}">
      <td>
        <button class="pin ${offer.pinned ? "active" : ""}" data-action="pin"
          data-stream="${stream.id}" data-offer="${offer.id}" data-pinned="${offer.pinned}"
          ${offer.removed ? "disabled" : ""} title="Закрепить вес">●</button>
        <strong>${escapeHtml(offer.name)}</strong> <small>#${offer.id}</small>
      </td>
      <td class="share">${offer.share}%</td>
      <td class="actions">
        ${offer.removed
          ? `<button data-action="restore" data-stream="${stream.id}" data-offer="${offer.id}">Bring back</button>`
          : `<button class="danger" data-action="remove" data-stream="${stream.id}" data-offer="${offer.id}">Remove</button>`}
      </td>
    </tr>`).join("");
}

function streamCard(stream) {
  const options = offerOptions.map(item =>
    `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
  return `
    <article class="stream ${stream.dirty ? "dirty" : ""}" data-stream-card="${stream.id}">
      <div class="stream-head">
        <div class="stream-title">
          <strong>${escapeHtml(stream.name)}</strong>
          <small>#${stream.id}</small>
          ${stream.dirty ? '<span class="badge">Черновик</span>' : ""}
        </div>
        <div class="stream-actions">
          ${stream.dirty ? `
            <button class="secondary" data-action="cancel" data-stream="${stream.id}">Cancel</button>
            <button data-action="push" data-stream="${stream.id}">Push to KT</button>` : ""}
        </div>
      </div>
      ${stream.has_offers ? `
        <table class="offers">
          <thead><tr><th>Оффер</th><th>Вес</th><th></th></tr></thead>
          <tbody>${offerRows(stream)}</tbody>
        </table>
        <form class="add-offer" data-stream="${stream.id}">
          <input type="number" min="1" required list="offers-${stream.id}" placeholder="ID оффера">
          <datalist id="offers-${stream.id}">${options}</datalist>
          <button type="submit">Добавить</button>
        </form>` :
        '<div class="streams empty">Поток без офферов — содержимое не редактируется.</div>'}
    </article>`;
}

function render() {
  if (!currentCampaign) return;
  streamsRoot.className = "streams";
  streamsRoot.innerHTML = currentCampaign.streams.map(streamCard).join("");
}

function replaceStream(updated) {
  const index = currentCampaign.streams.findIndex(item => item.id === updated.id);
  currentCampaign.streams[index] = updated;
  render();
}

async function fetchStreams() {
  if (!campaignSelect.value) throw new Error("Выберите кампанию");
  streamsRoot.className = "streams empty";
  streamsRoot.textContent = "Загрузка…";
  await loadOffers();
  currentCampaign = await api(`/api/campaigns/${campaignSelect.value}/fetch`, { method: "POST" });
  render();
}

document.querySelector("#create-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const form = new FormData(event.currentTarget);
  try {
    const campaign = await api("/api/campaigns", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        geo: form.get("geo"),
        offer_id: Number(form.get("offer_id")),
      }),
    });
    await loadCampaigns(campaign.id);
    await fetchStreams();
    event.currentTarget.reset();
    notify(`Кампания ${campaign.name} создана`);
  } catch (error) {
    notify(error.message, true);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#refresh-campaigns").addEventListener("click", async () => {
  try { await loadCampaigns(campaignSelect.value); }
  catch (error) { notify(error.message, true); }
});

document.querySelector("#fetch-streams").addEventListener("click", async () => {
  try { await fetchStreams(); notify("Потоки синхронизированы с Keitaro"); }
  catch (error) { notify(error.message, true); }
});

streamsRoot.addEventListener("submit", async event => {
  if (!event.target.matches(".add-offer")) return;
  event.preventDefault();
  const streamId = event.target.dataset.stream;
  const offerId = Number(event.target.querySelector("input").value);
  try {
    replaceStream(await api(`/api/streams/${streamId}/offers`, {
      method: "POST", body: JSON.stringify({ offer_id: offerId }),
    }));
  } catch (error) { notify(error.message, true); }
});

streamsRoot.addEventListener("click", async event => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const { action, stream, offer, pinned } = button.dataset;
  const routes = {
    remove: [`/api/streams/${stream}/offers/${offer}`, { method: "DELETE" }],
    restore: [`/api/streams/${stream}/offers/${offer}/restore`, { method: "POST" }],
    pin: [`/api/streams/${stream}/offers/${offer}/pin`, {
      method: "PUT", body: JSON.stringify({ pinned: pinned !== "true" }),
    }],
    cancel: [`/api/streams/${stream}/cancel`, { method: "POST" }],
    push: [`/api/streams/${stream}/push`, { method: "POST" }],
  };
  try {
    button.disabled = true;
    replaceStream(await api(...routes[action]));
    if (action === "push") notify("Изменения опубликованы в Keitaro");
    if (action === "cancel") notify("Черновик отменён");
  } catch (error) {
    notify(error.message, true);
    button.disabled = false;
  }
});

loadCampaigns().catch(error => notify(error.message, true));

