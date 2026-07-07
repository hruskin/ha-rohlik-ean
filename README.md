# Rohlík EAN — nákup podle čárového kódu pro Home Assistant

Naskenuj (nebo zadej) EAN a produkt přistane v košíku na Rohlík.cz. Integrace
překládá čárové kódy na produkty Rohlíku — Rohlík totiž vyhledávání podle EANu
oficiálně nepodporuje.

Staví na integraci [HA-RohlikCZ](https://github.com/dvejsada/HA-RohlikCZ)
(@dvejsada), která obstarává přihlášení a košík. Tahle integrace přidává jen
EAN můstek.

## Jak to funguje

Překladová kaskáda — zkouší se postupně, dokud něco nevrátí produkt:

1. **Lokální cache** — jednou vyřešené EANy (automaticky i ručně potvrzené) se
   pamatují navždy v `.storage/rohlik_ean.cache`.
2. **Fulltext Rohlíku se samotným EANem** — část sortimentu má EANy
   v indexu; jediný výsledek = přesná shoda.
3. **OpenFoodFacts** — EAN → značka + název + gramáž, tím se hledá na Rohlíku
   a kandidáti se skórují (shoda značky 0.4, gramáže 0.4, názvu 0.2).
   Bez ověřené gramáže se nikdy nepřidává automaticky (klasická past:
   200 g vs. 500 g varianta téhož jogurtu).
4. **Ruční potvrzení** — trvalá notifikace s kandidáty; volba se službou
   `confirm_match` uloží do cache, takže příště jede krok 1.

## Požadavky

- Home Assistant 2024.x+
- Nainstalovaná a nakonfigurovaná integrace
  [HA-RohlikCZ](https://github.com/dvejsada/HA-RohlikCZ) (HACS)

## Instalace

1. HACS → Integrations → ⋮ → Custom repositories →
   `https://github.com/hruskin/ha-rohlik-ean` (kategorie Integration)
2. Nainstaluj **Rohlík EAN**, restartuj HA.
3. Nastavení → Zařízení a služby → Přidat integraci → **Rohlík EAN**.

## Služby

### `rohlik_ean.add_by_ean`

| pole | | |
|---|---|---|
| `ean` | povinné | 8–14 číslic |
| `quantity` | volitelné | počet kusů, výchozí 1 |
| `dry_run` | volitelné | jen vyhledat, nepřidávat do košíku |

Vrací response data (`status`, `product`, `confidence`, `candidates`, …)
a vystřelí event:

- `rohlik_ean_matched` — produkt rozpoznán (`ean`, `product_id`, `name`,
  `source`, `confidence`, `added`, `quantity`)
- `rohlik_ean_unresolved` — potřeba potvrzení nebo nenalezeno (`ean`,
  `status`, `candidates`, `metadata`, `quantity`)

### `rohlik_ean.confirm_match`

Naučí integraci mapování EAN → produkt (`ean`, `product_id`, volitelně
`name`); s `quantity > 0` produkt rovnou přidá do košíku.

### `rohlik_ean.forget_ean`

Smaže naučené mapování z cache (např. po chybném potvrzení).

## Možnosti (Nastavit u integrace)

- **Práh jistoty** (výchozí 0.75) — od jakého skóre se přidává automaticky.
- **Věřit jedinému EAN hitu** (výchozí ano) — jediný výsledek fulltextu pro
  samotný EAN se bere jako přesná shoda.
- **Notifikace pro nerozpoznané** (výchozí ano).

## Příklady

- [examples/dashboard.yaml](examples/dashboard.yaml) — ruční zadání EANu na
  dashboardu (fáze 1)
- [examples/unresolved_notification.yaml](examples/unresolved_notification.yaml)
  — actionable notifikace do mobilu s výběrem kandidáta jedním tapnutím
- [examples/barcode_scanner.yaml](examples/barcode_scanner.yaml) — napojení
  hardwarové čtečky ESP32 + GM67 (fáze 2)

## Omezení

- Neoficiální API Rohlíku (přes HA-RohlikCZ) — může se kdykoli změnit.
- České privátní značky (Miil, …) v OpenFoodFacts často chybí — poprvé je
  potvrdíš ručně, pak už jedou z cache.
- EAN se odesílá na world.openfoodfacts.org (nic jiného).
