/* Rohlík EAN — učicí panel.
 * Nahoře fronta čekajících skenů (hledání a přiřazení produktu),
 * dole naučená databáze (náhledy, editace, hromadné mazání).
 * Přiřazení POUZE učí mapování (nic nepřidává do košíku).
 */
class RohlikEanPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._items = [];
    this._mappings = {};
    this._filter = "";
    this._selected = new Set();
    this._editing = null; // EAN právě editovaného mapování
    this._editCandidates = [];
    this._imgs = {};
    this._imgsPending = new Set();
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

  /* ---------- data ---------- */

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
      this._offEnabled = !!(r.response && r.response.off_enabled);
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._renderMappings();
  }

  async _contribute(ean) {
    this._busy.add(ean);
    this._renderMappings();
    try {
      const r = await this._call("contribute_to_off", { ean }, true);
      const resp = (r && r.response) || {};
      if (resp.failed && resp.failed[ean]) {
        this._error = `OFF: ${resp.failed[ean]}`;
      } else {
        this._error = null;
      }
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._busy.delete(ean);
    this._loadMappings();
  }

  _collectImageIds() {
    const ids = [];
    for (const item of this._items)
      for (const c of item.candidates || []) ids.push(c.id);
    for (const m of Object.values(this._mappings)) ids.push(m.product_id);
    for (const c of this._editCandidates) ids.push(c.id);
    return ids.filter((i) => i != null);
  }

  async _ensureImages() {
    const missing = [
      ...new Set(
        this._collectImageIds().filter(
          (i) => !(i in this._imgs) && !this._imgsPending.has(i)
        )
      ),
    ];
    if (!missing.length) return;
    for (const i of missing) this._imgsPending.add(i);
    try {
      const r = await this._call(
        "get_product_images",
        { product_ids: missing },
        true
      );
      const images = (r.response && r.response.images) || {};
      // Cachujeme i null, ať se na chybějící obrázky neptáme dokola.
      for (const i of missing) this._imgs[i] = images[String(i)] || null;
    } catch (e) {
      for (const i of missing) this._imgs[i] = null;
    }
    for (const i of missing) this._imgsPending.delete(i);
    this._renderRows();
    this._renderMappings();
  }

  /* ---------- akce ---------- */

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
      if (this._editing === ean) {
        this._editing = null;
        this._editCandidates = [];
      }
    } catch (e) {
      this._error = e.message || String(e);
      this._load();
    }
    this._busy.delete(ean);
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

  async _forgetSelected() {
    const eans = [...this._selected];
    if (!eans.length) return;
    if (!confirm(`Smazat ${eans.length} vybraných mapování?`)) return;
    try {
      await this._call("forget_eans", { eans });
      this._selected.clear();
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
      this._loadMappings();
    }
  }

  async _editSearch(name) {
    if (!name || !this._editing) return;
    try {
      const r = await this._call("search_products", { name }, true);
      this._editCandidates = (r.response && r.response.candidates) || [];
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._renderMappings();
  }

  /* ---------- render ---------- */

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
        .ean { font-family: monospace; font-size:14px; font-weight:600; }
        .meta { color: var(--secondary-text-color); font-size:12px; margin-top:4px; }
        .metaimg { margin-top:8px; }
        .search { display:flex; gap:8px; margin-bottom:8px; }
        .search input { flex:1; padding:8px 10px; border-radius:8px; border:1px solid var(--divider-color,#ccc);
                        background: var(--secondary-background-color, #fafafa); color: var(--primary-text-color); font-size:14px; }
        button { border:none; border-radius:8px; padding:8px 12px; cursor:pointer; font-size:13px;
                 background: var(--primary-color, #03a9f4); color:#fff; }
        button.ghost { background:transparent; color: var(--secondary-text-color); border:1px solid var(--divider-color,#ccc); }
        button.danger { background: transparent; color: var(--error-color, #db4437); border:1px solid var(--error-color, #db4437); }
        button:disabled { opacity:.5; cursor:default; }
        .cands { display:flex; flex-direction:column; gap:6px; }
        .cand { display:flex; align-items:center; gap:10px;
                border:1px solid var(--divider-color,#e0e0e0); border-radius:8px; padding:6px 10px; }
        .cand .nm { font-size:13px; flex:1; }
        .cand .pr { color: var(--secondary-text-color); font-size:12px; white-space:nowrap; }
        .cand button { padding:5px 10px; }
        .thumb { width:44px; height:44px; object-fit:contain; border-radius:6px; flex:none;
                 background:#fff; border:1px solid var(--divider-color,#e0e0e0); }
        .thumb.ph { display:inline-flex; align-items:center; justify-content:center;
                    color: var(--secondary-text-color); font-size:16px; }
        .hint { color: var(--secondary-text-color); font-size:12px; font-style:italic; }
        .busy { opacity:.55; pointer-events:none; }
        h2 { font-size: 17px; font-weight: 500; margin: 28px 0 10px; }
        h2 .count { color: var(--secondary-text-color); font-weight: 400; font-size: 13px; }
        .mtools { display:flex; gap:10px; align-items:center; margin-bottom:10px; flex-wrap:wrap; }
        .mtools label { display:flex; align-items:center; gap:6px; font-size:13px; color: var(--secondary-text-color); cursor:pointer; }
        .filter { flex:1; min-width:200px; box-sizing:border-box; padding:8px 10px;
                  border-radius:8px; border:1px solid var(--divider-color,#ccc);
                  background: var(--secondary-background-color, #fafafa); color: var(--primary-text-color); font-size:14px; }
        .map { background: var(--card-background-color, #fff); border-radius:10px; padding:8px 14px; margin-bottom:8px;
               box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); }
        .maprow { display:grid; grid-template-columns: 24px 44px 1fr 90px auto; gap:12px; align-items:center; }
        @media (max-width: 720px) { .maprow { grid-template-columns: 24px 44px 1fr auto; } .maprow .dt { display:none; } }
        .map .nm { font-size:13px; }
        .map .pid { color: var(--secondary-text-color); font-size:12px; }
        .map .dt { color: var(--secondary-text-color); font-size:12px; }
        .map .acts { display:flex; gap:6px; align-items:center; }
        .offok { color: var(--secondary-text-color); font-size:11px; white-space:nowrap;
                 border:1px solid var(--divider-color,#e0e0e0); border-radius:6px; padding:3px 6px; }
        .editbox { margin-top:10px; padding-top:10px; border-top:1px solid var(--divider-color,#e0e0e0); }
        input[type="checkbox"] { width:16px; height:16px; cursor:pointer; }
      </style>
      <h1>Rohlík EAN — učení kódů</h1>
      <div class="sub">Přiřazení pouze naučí mapování EAN → produkt. Do košíku se nic nepřidává — nákup proběhne až dalším skenem.</div>
      <div id="error"></div>
      <div id="rows"></div>
      <h2>Naučené kódy <span class="count" id="mcount"></span></h2>
      <div class="mtools">
        <label><input type="checkbox" id="selall"> vybrat vše</label>
        <button class="danger" id="delsel" disabled>Smazat vybrané</button>
        <input class="filter" id="mfilter" placeholder="Filtrovat podle EANu nebo názvu…">
      </div>
      <div id="maps"></div>
    `;
    this.shadowRoot.getElementById("mfilter").addEventListener("input", (ev) => {
      this._filter = ev.target.value.trim().toLowerCase();
      this._renderMappings();
    });
    this.shadowRoot.getElementById("selall").addEventListener("change", (ev) => {
      const entries = this._filteredMappings();
      if (ev.target.checked) for (const [ean] of entries) this._selected.add(ean);
      else for (const [ean] of entries) this._selected.delete(ean);
      this._renderMappings();
    });
    this.shadowRoot
      .getElementById("delsel")
      .addEventListener("click", () => this._forgetSelected());
  }

  // Only load images over https from trusted hosts. OpenFoodFacts image
  // URLs are community-editable, so an unrestricted <img src> would let a
  // third party trigger an outbound request (IP + scan leak).
  _safeImg(url) {
    try {
      const u = new URL(url);
      if (u.protocol !== "https:") return null;
      const host = u.hostname.toLowerCase();
      const ok = [
        "cdn.rohlik.cz",
        "rohlik.cz",
        "openfoodfacts.org",
        "static.openfoodfacts.org",
        "images.openfoodfacts.org",
      ];
      return ok.some((h) => host === h || host.endsWith("." + h)) ? url : null;
    } catch (e) {
      return null;
    }
  }

  _thumb(productId) {
    const url = this._safeImg(this._imgs[productId]);
    if (url) {
      const img = document.createElement("img");
      img.className = "thumb";
      img.src = url;
      img.loading = "lazy";
      img.alt = "";
      return img;
    }
    const ph = document.createElement("span");
    ph.className = "thumb ph";
    ph.textContent = "🛒";
    return ph;
  }

  _candidateRow(ean, c) {
    const div = document.createElement("div");
    div.className = "cand";
    div.appendChild(this._thumb(c.id));
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = `${c.name || "ID " + c.id} (${c.amount || "?"})`;
    const pr = document.createElement("span");
    pr.className = "pr";
    pr.textContent = c.price || "";
    const pick = document.createElement("button");
    pick.textContent = "Přiřadit";
    pick.addEventListener("click", () => this._assign(ean, c));
    div.append(nm, pr, pick);
    return div;
  }

  _renderRows() {
    const err = this.shadowRoot.getElementById("error");
    if (err)
      err.innerHTML = this._error
        ? `<div class="error">${this._esc(this._error)}</div>`
        : "";

    const root = this.shadowRoot.getElementById("rows");
    if (!root) return;
    if (!this._items.length) {
      root.innerHTML = `<div class="empty">Fronta je prázdná — žádný kód nečeká na naučení. 🎉</div>`;
      this._ensureImages();
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
      const metaImg = item.metadata && this._safeImg(item.metadata.image);
      if (metaImg) {
        const mi = document.createElement("img");
        mi.className = "thumb metaimg";
        mi.src = metaImg;
        mi.loading = "lazy";
        mi.alt = "";
        left.appendChild(mi);
      }

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
        for (const c of item.candidates)
          cands.appendChild(this._candidateRow(item.ean, c));
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
    this._ensureImages();
  }

  _filteredMappings() {
    let entries = Object.entries(this._mappings);
    if (this._filter) {
      entries = entries.filter(
        ([ean, m]) =>
          ean.includes(this._filter) ||
          (m.name || "").toLowerCase().includes(this._filter)
      );
    }
    // Nejnovější nahoře.
    entries.sort((a, b) =>
      (b[1].cached_at || "").localeCompare(a[1].cached_at || "")
    );
    return entries;
  }

  _renderMappings() {
    const count = this.shadowRoot.getElementById("mcount");
    const root = this.shadowRoot.getElementById("maps");
    const delsel = this.shadowRoot.getElementById("delsel");
    const selall = this.shadowRoot.getElementById("selall");
    if (!count || !root) return;

    // Výběr očisti od EANů, které už neexistují.
    for (const ean of [...this._selected])
      if (!(ean in this._mappings)) this._selected.delete(ean);
    if (this._editing && !(this._editing in this._mappings)) {
      this._editing = null;
      this._editCandidates = [];
    }

    const all = Object.keys(this._mappings).length;
    const entries = this._filteredMappings();
    count.textContent = this._filter ? `(${entries.length} z ${all})` : `(${all})`;
    delsel.disabled = this._selected.size === 0;
    delsel.textContent = this._selected.size
      ? `Smazat vybrané (${this._selected.size})`
      : "Smazat vybrané";
    selall.checked =
      entries.length > 0 && entries.every(([ean]) => this._selected.has(ean));

    if (!entries.length) {
      root.innerHTML = `<div class="hint" style="padding:4px 2px;">${
        this._filter ? "Filtru nic neodpovídá." : "Zatím žádné naučené kódy."
      }</div>`;
      this._ensureImages();
      return;
    }
    root.innerHTML = "";
    for (const [ean, m] of entries) {
      const card = document.createElement("div");
      card.className = "map";
      const row = document.createElement("div");
      row.className = "maprow";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = this._selected.has(ean);
      cb.addEventListener("change", () => {
        if (cb.checked) this._selected.add(ean);
        else this._selected.delete(ean);
        this._renderMappings();
      });

      const thumb = this._thumb(m.product_id);

      const nm = document.createElement("span");
      nm.className = "nm";
      nm.innerHTML = `<span class="ean">${this._esc(ean)}</span><br>${this._esc(
        m.name || "(bez názvu)"
      )} <span class="pid">· ID ${this._esc(m.product_id)}</span>`;

      const dt = document.createElement("span");
      dt.className = "dt";
      dt.textContent = m.cached_at || "";

      const acts = document.createElement("div");
      acts.className = "acts";
      if (m.off_contributed) {
        const badge = document.createElement("span");
        badge.className = "offok";
        badge.textContent = "OFF ✓";
        badge.title = `Odesláno do OpenFoodFacts ${m.off_contributed}`;
        acts.appendChild(badge);
      } else if (this._offEnabled) {
        const off = document.createElement("button");
        off.className = "ghost";
        off.textContent = "→ OFF";
        off.title = "Odeslat název/značku/gramáž do OpenFoodFacts";
        off.addEventListener("click", () => this._contribute(ean));
        acts.appendChild(off);
      }
      const edit = document.createElement("button");
      edit.className = "ghost";
      edit.textContent = this._editing === ean ? "Zavřít" : "Upravit";
      edit.addEventListener("click", () => {
        this._editing = this._editing === ean ? null : ean;
        this._editCandidates = [];
        this._renderMappings();
      });
      const del = document.createElement("button");
      del.className = "danger";
      del.textContent = "Smazat";
      del.addEventListener("click", () => this._forget(ean, m.name));
      acts.append(edit, del);

      row.append(cb, thumb, nm, dt, acts);
      card.appendChild(row);

      if (this._editing === ean) {
        const box = document.createElement("div");
        box.className = "editbox";
        const search = document.createElement("div");
        search.className = "search";
        const input = document.createElement("input");
        input.placeholder = "Hledat nový produkt… (Enter)";
        input.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") this._editSearch(input.value.trim());
        });
        const btn = document.createElement("button");
        btn.textContent = "Hledat";
        btn.addEventListener("click", () => this._editSearch(input.value.trim()));
        search.append(input, btn);
        box.appendChild(search);

        const cands = document.createElement("div");
        cands.className = "cands";
        if (this._editCandidates.length) {
          for (const c of this._editCandidates)
            cands.appendChild(this._candidateRow(ean, c));
        } else {
          cands.innerHTML = `<span class="hint">Vyhledej produkt, kterým chceš mapování nahradit.</span>`;
        }
        box.appendChild(cands);
        card.appendChild(box);
        requestAnimationFrame(() => input.focus());
      }

      root.appendChild(card);
    }
    this._ensureImages();
  }

  _esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
}

customElements.define("rohlik-ean-panel", RohlikEanPanel);
