/* Rohlík EAN — učicí panel.
 * Vlevo čekající EANy, vpravo hledání a přiřazení produktu.
 * Přiřazení POUZE učí mapování (nic nepřidává do košíku).
 */
class RohlikEanPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._items = [];
    this._mappings = {};
    this._filter = "";
    this._busy = new Set();
    this._error = null;
    this._ready = false;
    this._unsubs = [];
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._ready) {
      this._ready = true;
      this._renderShell();
      this._load();
      this._subscribe();
    }
  }

  disconnectedCallback() {
    for (const u of this._unsubs) u();
    this._unsubs = [];
  }

  async _subscribe() {
    this._unsubs.push(
      await this._hass.connection.subscribeEvents(
        () => this._load(),
        "rohlik_ean_queue_changed"
      ),
      await this._hass.connection.subscribeEvents(
        () => this._loadMappings(),
        "rohlik_ean_cache_changed"
      )
    );
  }

  async _call(service, data, returnResponse = false) {
    return this._hass.callWS({
      type: "call_service",
      domain: "rohlik_ean",
      service,
      service_data: data,
      return_response: returnResponse,
    });
  }

  async _load() {
    try {
      const r = await this._call("get_queue", {}, true);
      this._items = (r.response && r.response.items) || [];
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._renderRows();
    this._loadMappings();
  }

  async _loadMappings() {
    try {
      const r = await this._call("get_mappings", {}, true);
      this._mappings = (r.response && r.response.mappings) || {};
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._renderMappings();
  }

  async _forget(ean, name) {
    if (!confirm(`Smazat naučené mapování ${ean} → ${name || "?"}?`)) return;
    try {
      await this._call("forget_ean", { ean });
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
      this._loadMappings();
    }
  }

  async _search(ean, name) {
    if (!name) return;
    this._busy.add(ean);
    this._renderRows();
    try {
      await this._call("search_by_name", { ean, name }, true);
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._busy.delete(ean);
    this._load();
  }

  async _assign(ean, candidate) {
    this._busy.add(ean);
    this._renderRows();
    try {
      // Učení mapování — bez quantity, tedy bez košíku.
      await this._call("confirm_match", {
        ean,
        product_id: candidate.id,
        name: candidate.name || undefined,
      });
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
      this._busy.delete(ean);
      this._load();
    }
  }

  async _discard(ean) {
    this._busy.add(ean);
    this._renderRows();
    try {
      await this._call("discard_scan", { ean });
    } catch (e) {
      this._error = e.message || String(e);
      this._busy.delete(ean);
      this._load();
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:16px; max-width:1100px; margin:0 auto;
                color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
        h1 { font-size: 22px; font-weight: 400; margin: 4px 0 2px; }
        .sub { color: var(--secondary-text-color); margin-bottom: 16px; font-size: 13px; }
        .error { background: var(--error-color, #db4437); color:#fff; padding:8px 12px; border-radius:8px; margin-bottom:12px; }
        .empty { background: var(--card-background-color, #fff); border-radius:12px; padding:32px; text-align:center;
                 color: var(--secondary-text-color); box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); }
        .row { background: var(--card-background-color, #fff); border-radius:12px; padding:14px 16px; margin-bottom:12px;
               box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12));
               display:grid; grid-template-columns: 220px 1fr auto; gap:14px; align-items:start; }
        @media (max-width: 720px) { .row { grid-template-columns: 1fr; } }
        .ean { font-family: monospace; font-size:15px; font-weight:600; }
        .meta { color: var(--secondary-text-color); font-size:12px; margin-top:4px; }
        .search { display:flex; gap:8px; margin-bottom:8px; }
        .search input { flex:1; padding:8px 10px; border-radius:8px; border:1px solid var(--divider-color,#ccc);
                        background: var(--secondary-background-color, #fafafa); color: var(--primary-text-color); font-size:14px; }
        button { border:none; border-radius:8px; padding:8px 12px; cursor:pointer; font-size:13px;
                 background: var(--primary-color, #03a9f4); color:#fff; }
        button.ghost { background:transparent; color: var(--secondary-text-color); border:1px solid var(--divider-color,#ccc); }
        button:disabled { opacity:.5; cursor:default; }
        .cands { display:flex; flex-direction:column; gap:6px; }
        .cand { display:flex; justify-content:space-between; align-items:center; gap:10px;
                border:1px solid var(--divider-color,#e0e0e0); border-radius:8px; padding:6px 10px; }
        .cand .nm { font-size:13px; }
        .cand .pr { color: var(--secondary-text-color); font-size:12px; white-space:nowrap; }
        .cand button { padding:5px 10px; }
        .hint { color: var(--secondary-text-color); font-size:12px; font-style:italic; }
        .busy { opacity:.55; pointer-events:none; }
        h2 { font-size: 17px; font-weight: 500; margin: 28px 0 10px; }
        h2 .count { color: var(--secondary-text-color); font-weight: 400; font-size: 13px; }
        .filter { width: 100%; box-sizing: border-box; padding:8px 10px; margin-bottom:10px;
                  border-radius:8px; border:1px solid var(--divider-color,#ccc);
                  background: var(--secondary-background-color, #fafafa); color: var(--primary-text-color); font-size:14px; }
        .map { background: var(--card-background-color, #fff); border-radius:10px; padding:10px 14px; margin-bottom:8px;
               box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12));
               display:grid; grid-template-columns: 160px 1fr 90px auto; gap:12px; align-items:center; }
        @media (max-width: 720px) { .map { grid-template-columns: 1fr auto; } .map .dt { display:none; } }
        .map .nm { font-size:13px; }
        .map .pid { color: var(--secondary-text-color); font-size:12px; }
        .map .dt { color: var(--secondary-text-color); font-size:12px; }
        button.danger { background: transparent; color: var(--error-color, #db4437); border:1px solid var(--error-color, #db4437); }
      </style>
      <h1>Rohlík EAN — učení kódů</h1>
      <div class="sub">Přiřazení pouze naučí mapování EAN → produkt. Do košíku se nic nepřidává — nákup proběhne až dalším skenem.</div>
      <div id="error"></div>
      <div id="rows"></div>
      <h2>Naučené kódy <span class="count" id="mcount"></span></h2>
      <input class="filter" id="mfilter" placeholder="Filtrovat podle EANu nebo názvu…">
      <div id="maps"></div>
    `;
    this.shadowRoot.getElementById("mfilter").addEventListener("input", (ev) => {
      this._filter = ev.target.value.trim().toLowerCase();
      this._renderMappings();
    });
  }

  _renderMappings() {
    const count = this.shadowRoot.getElementById("mcount");
    const root = this.shadowRoot.getElementById("maps");
    if (!count || !root) return;

    let entries = Object.entries(this._mappings);
    count.textContent = `(${entries.length})`;
    if (this._filter) {
      entries = entries.filter(
        ([ean, m]) =>
          ean.includes(this._filter) ||
          (m.name || "").toLowerCase().includes(this._filter)
      );
    }
    // Nejnovější nahoře.
    entries.sort((a, b) => (b[1].cached_at || "").localeCompare(a[1].cached_at || ""));

    if (!entries.length) {
      root.innerHTML = `<div class="hint" style="padding:4px 2px;">${
        this._filter ? "Filtru nic neodpovídá." : "Zatím žádné naučené kódy."
      }</div>`;
      return;
    }
    root.innerHTML = "";
    for (const [ean, m] of entries) {
      const row = document.createElement("div");
      row.className = "map";
      const eanEl = document.createElement("span");
      eanEl.className = "ean";
      eanEl.textContent = ean;
      const nm = document.createElement("span");
      nm.className = "nm";
      nm.innerHTML = `${this._esc(m.name || "(bez názvu)")} <span class="pid">· ID ${this._esc(m.product_id)}</span>`;
      const dt = document.createElement("span");
      dt.className = "dt";
      dt.textContent = m.cached_at || "";
      const del = document.createElement("button");
      del.className = "danger";
      del.textContent = "Smazat";
      del.addEventListener("click", () => this._forget(ean, m.name));
      row.append(eanEl, nm, dt, del);
      root.appendChild(row);
    }
  }

  _renderRows() {
    const err = this.shadowRoot.getElementById("error");
    err.innerHTML = this._error ? `<div class="error">${this._esc(this._error)}</div>` : "";

    const root = this.shadowRoot.getElementById("rows");
    if (!this._items.length) {
      root.innerHTML = `<div class="empty">Fronta je prázdná — žádný kód nečeká na naučení. 🎉</div>`;
      return;
    }
    root.innerHTML = "";
    for (const item of this._items) {
      const row = document.createElement("div");
      row.className = "row" + (this._busy.has(item.ean) ? " busy" : "");

      const left = document.createElement("div");
      const metaTxt = item.metadata
        ? `${item.metadata.brand || ""} ${item.metadata.name || ""} (${item.metadata.quantity || "?"})`.trim()
        : "kód nezná OpenFoodFacts";
      left.innerHTML = `<div class="ean">${this._esc(item.ean)}</div><div class="meta">${this._esc(metaTxt)}</div>`;

      const mid = document.createElement("div");
      const search = document.createElement("div");
      search.className = "search";
      const input = document.createElement("input");
      input.placeholder = "Hledat na Rohlíku… (Enter)";
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") this._search(item.ean, input.value.trim());
      });
      const btn = document.createElement("button");
      btn.textContent = "Hledat";
      btn.addEventListener("click", () => this._search(item.ean, input.value.trim()));
      search.append(input, btn);
      mid.appendChild(search);

      const cands = document.createElement("div");
      cands.className = "cands";
      if (item.candidates && item.candidates.length) {
        for (const c of item.candidates) {
          const div = document.createElement("div");
          div.className = "cand";
          const nm = document.createElement("span");
          nm.className = "nm";
          nm.textContent = `${c.name || "ID " + c.id} (${c.amount || "?"})`;
          const pr = document.createElement("span");
          pr.className = "pr";
          pr.textContent = c.price || "";
          const pick = document.createElement("button");
          pick.textContent = "Přiřadit";
          pick.addEventListener("click", () => this._assign(item.ean, c));
          div.append(nm, pr, pick);
          cands.appendChild(div);
        }
      } else {
        cands.innerHTML = `<span class="hint">Žádní kandidáti — napiš název a hledej.</span>`;
      }
      mid.appendChild(cands);

      const right = document.createElement("div");
      const discard = document.createElement("button");
      discard.className = "ghost";
      discard.textContent = "Zahodit";
      discard.addEventListener("click", () => this._discard(item.ean));
      right.appendChild(discard);

      row.append(left, mid, right);
      root.appendChild(row);
    }
  }

  _esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
}

customElements.define("rohlik-ean-panel", RohlikEanPanel);
