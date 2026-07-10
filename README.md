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
4. **Ruční naučení** — sken se zařadí do fronty a naučíš ho v panelu
   **Rohlík EAN** (boční menu). Učení pouze uloží mapování do cache —
   **do košíku se při něm nic nepřidává**; nákup proběhne dalším skenem
   (ten už jede krokem 1).

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
- `rohlik_ean_add_failed` — produkt rozpoznán, ale nepřidal se (typicky
  vyprodáno; `ean`, `product_id`, `name`, `quantity`, `reason`). Naučené
  mapování se v tom případě zachovává. Pokud Rohlík produkt nahradil
  novým ID, integrace to pozná (přeresolvuje mimo cache), přeučí se
  a přidá náhradu automaticky.

Úspěšné přidání se ověřuje proti odpovědi košíku (`added_products`) —
`added: true` znamená, že produkt v košíku opravdu je. Název produktu se
do události doplňuje i pro starší mapování uložená beze jména (z obsahu
košíku), takže jde použít pro hlasová oznámení — viz
[examples/announce.yaml](examples/announce.yaml).

### `rohlik_ean.confirm_match`

Naučí integraci mapování EAN → produkt (`ean`, `product_id`, volitelně
`name`). Učení do košíku nesahá; jen s explicitním `quantity > 0`
produkt rovnou i přidá.

### Služby pro učicí panel

`get_queue` (fronta skenů), `get_mappings` (naučená databáze),
`discard_scan` (zahodí sken; `ean` volitelně, jinak nejstarší),
`forget_eans` (hromadné smazání mapování, `eans` = seznam),
`search_products` (hledání bez zásahu do fronty, pro editaci),
`get_product_images` (`product_ids` → URL náhledů z veřejného CDN).

### `rohlik_ean.search_by_name`

Ruční hledání pro čekající sken (`name` povinné; `ean` volitelné — bez něj
se cílí na aktuální sken ve frontě; `quantity` volitelně přepíše množství
pro potvrzení). Totéž, co dělá entita **Hledat název**.

### `rohlik_ean.forget_ean`

Smaže naučené mapování z cache (např. po chybném potvrzení).

## Učicí panel

Integrace přidává do bočního menu HA panel **Rohlík EAN**: tabulka
čekajících kódů — vlevo EAN s nápovědou z OpenFoodFacts, vpravo hledání
na Rohlíku a kandidáti k přiřazení jedním klikem. Přiřazení naučí
mapování (bez košíku), řádek zmizí a panel se aktualizuje živě s každým
novým skenem. Tlačítko Zahodit odstraní omylové skeny.

Pod frontou je sekce **Naučené kódy**: celá databáze EAN → produkt
s náhledy, datem naučení a filtrováním podle EANu/názvu. Každé mapování
jde **Upravit** (vyhledáš nový produkt a přiřadíš — např. po chybném
přiřazení nebo když Rohlík produkt vyměnil) nebo **Smazat**; checkboxy
+ „vybrat vše" umožňují **hromadné mazání** vybraných mapování.

Panel zobrazuje **náhledové obrázky produktů** — u kandidátů a naučených
kódů z veřejného CDN Rohlíku (`cdn.rohlik.cz`, bez přihlášení), u
naskenovaného kódu z OpenFoodFacts, pokud ho zná.

## Entity (potvrzovací fronta)

Nerozpoznané skeny s kandidáty čekají v perzistentní frontě (přežije
restart HA) a integrace k ní vytváří zařízení **Rohlík EAN** s entitami:

- **sensor Čeká na potvrzení** — počet čekajících skenů; atributy nesou
  EAN, metadata z OpenFoodFacts a kandidáty aktuálního (nejstaršího) skenu.
- **select Kandidát** — kandidáti s plným názvem, gramáží a cenou.
  Výběr možnosti = naučení mapování (do košíku se nepřidává).
- **text Hledat název** — ruční hledání: napiš název produktu a Rohlík se
  jím prohledá; výsledky se nabídnou jako kandidáti aktuálního skenu.
  Nutné u produktů, které nezná OpenFoodFacts ani fulltext (privátní
  značky) — takové skeny čekají ve frontě s prázdnými kandidáty.
- **button Zahodit čekající sken** — aktuální sken zahodí bez učení.

Hotová podmíněná karta: [examples/confirm_card.yaml](examples/confirm_card.yaml).

## Možnosti (Nastavit u integrace)

- **Práh jistoty** (výchozí 0.75) — od jakého skóre se přidává automaticky.
- **Věřit jedinému EAN hitu** (výchozí ano) — jediný výsledek fulltextu pro
  samotný EAN se bere jako přesná shoda.
- **Notifikace pro nerozpoznané** (výchozí ano).

## Příklady

- [examples/dashboard.yaml](examples/dashboard.yaml) — ruční zadání EANu na
  dashboardu (fáze 1)
- [examples/confirm_card.yaml](examples/confirm_card.yaml) — podmíněná
  karta s potvrzovací frontou (plné názvy kandidátů)
- [examples/unresolved_notification.yaml](examples/unresolved_notification.yaml)
  — actionable notifikace do mobilu s výběrem kandidáta jedním tapnutím
- [examples/announce.yaml](examples/announce.yaml) — hlasové oznámení
  výsledku skenu přes TTS (Google Nest apod.)
- [examples/barcode_scanner.yaml](examples/barcode_scanner.yaml) — napojení
  hardwarové čtečky ESP32 + GM67 (fáze 2)

## Omezení

- Neoficiální API Rohlíku (přes HA-RohlikCZ) — může se kdykoli změnit.
- České privátní značky (Miil, …) v OpenFoodFacts často chybí — poprvé je
  dohledáš ručně přes **Hledat název**, pak už jedou z cache.
- EAN se odesílá na world.openfoodfacts.org (nic jiného).
