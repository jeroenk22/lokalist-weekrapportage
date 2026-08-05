# Weekrapportage-dashboard

Webdashboard waarmee collega's zonder Python een bestaand weekrapport van
De Lokalist opnieuw kunnen genereren.

## Waarom deze opzet

De eis was dat de kwaliteit **exact gelijk** is aan die van het Python-script dat
elke zondag om 23:30 draait. Daarom bouwt dit dashboard het rapport niet zelf na:
het start dezelfde Python-engine en toont de voortgang in de browser.

```
Browser (collega, geen installatie nodig)
   │
   ▼
React-dashboard  ──►  Express/TypeScript  ──►  scripts/web_runner.py
                          (op de 105)              │
                                                   ▼
                                    query.py · genereer_rapport.py
                                    mendrix_client.py · mailer.py
                                                   │
                                    SQL · SOAP · REST · SMTP  ──►  MendriX
```

De PDF komt dus uit dezelfde `reportlab`-code, de data uit dezelfde SQL en de
order uit dezelfde XML als bij de automatische run.

## Bestaande code is niet gewijzigd

`scripts/run_weekrapportage.py` — de zondagrun — is bewust **ongemoeid** gelaten.
De gedeelde onderdelen staan daarom in nieuwe modules
(`mendrix_client.py`, `verzamelorder.py`), naast de originelen.

Die duplicatie wordt bewaakt door `tests/unit/test_verzamelorder_drift.py`: die
vergelijkt beide implementaties direct met elkaar. Wijzigt er één, dan valt de
test om en is het verschil meteen zichtbaar.

## Wat het dashboard doet

1. Toont alle actieve verzamelorders uit MendriX, nieuwste eerst, met achter het
   ordernummer `dagnaam dd maandnaam jaar (automatisch)` of `(handmatig)`.
2. Klik je er één aan, dan opent een modal met de ontvangers uit `.env`. Adressen
   kun je uitvinken, aanpassen (het Aan-adres, bijv. naar je priveadres) of
   aanvullen.
3. Na een expliciete bevestiging draait de keten in 7 stappen, live zichtbaar.
4. Daarna sluit je de modal en is de lijst automatisch bijgewerkt.

### Volgorde en vangnet

Bewust **eerst nieuw, dan oud weg**:

| Stap | Actie |
|------|-------|
| 1 | orders ophalen uit de database |
| 2 | PDF genereren |
| 3 | nieuwe verzamelorder aanmaken |
| 4 | order-XML ophalen |
| 5 | PDF + ordernummers.txt in het dossier |
| 6 | rapport e-mailen |
| 7 | **pas nu** de oude verzamelorder verwijderen |

Faalt stap 4, 5 of 6, dan wordt de zojuist aangemaakte order teruggedraaid en
blijft de oorspronkelijke verzamelorder gewoon bestaan. Er gaat nooit een order
verloren door een halverwege mislukte run.

### Handmatige markering

De nieuwe order krijgt in het `<Notes>`-veld (kolom `dbo.Orders.Diversen`) de
tekst `[HANDMATIG HERGENEREERD] … De eerder aangemaakte verzamelorder <nummer>
is daarbij verwijderd.` Daaraan herkent het dashboard bij het volgende laden dat
deze order handmatig is gedraaid — het toont dan `(handmatig)` achter het
ordernummer — en blijft terug te vinden welke order vervangen is.

### Factuurgrendel

Een verzamelorder die op een factuur staat (`dbo.Orders.InvKey` gevuld,
`InvStatus` 20) kan **niet** hergenereerd worden. Hergenereren verwijdert de
order en maakt een nieuwe met een ander ordernummer aan; de factuurregel zou dan
naar een verdwenen order verwijzen.

Zulke orders blijven zichtbaar in de lijst met een `gefactureerd`-badge en het
factuurnummer, maar zijn niet aanklikbaar. De echte controle staat in
`web_runner.py` en niet alleen in de UI — een browser is geen beveiliging.

In de praktijk betekent dit dat alleen de lopende, nog niet gefactureerde week
hergenereerd kan worden. Precies waarvoor dit dashboard bedoeld is.

### Allowlist op de ontvangers

In de modal kun je het Aan-adres aanpassen en adressen toevoegen. Het rapport
bevat klantgegevens van De Lokalist, dus `DASHBOARD_EMAIL_DOMEINEN` in `.env`
begrenst waar het heen mag:

```
DASHBOARD_EMAIL_DOMEINEN=lokalist.nl,ophaaldienstmiedema.nl,jeroen@gmail.com
```

Elke regel is óf een domein óf één volledig adres — het onderscheid zit in de
apenstaart:

| Regel | Betekenis |
|---|---|
| `lokalist.nl` of `@lokalist.nl` | elk adres op dat domein |
| `jeroen@gmail.com` | alleen dit ene adres; `iemand.anders@gmail.com` blijft geweigerd |

Die tweede vorm bestaat voor het testscenario waar het bewerkbare Aan-veld voor
gemaakt is: het rapport eerst naar jezelf sturen om te zien hoe het eruitziet,
zonder een heel publiek maildomein als `gmail.com` open te zetten.

- **Leeg = geen begrenzing** — het gedrag van vóór deze controle, zodat een
  bestaande installatie niet stilvalt.
- De adressen uit `EMAIL_ONTVANGERS`/`EMAIL_CC`/`EMAIL_BCC` en
  `DASHBOARD_EMAIL_UITGEVINKT` mogen altijd, ook buiten de lijst. Anders zou een
  krappe lijst de gewone ontvangers blokkeren.
- De bindende controle staat in `email_allowlist.py`, aangeroepen vanuit
  `web_runner.py` vóór er iets in MendriX gebeurt. De UI kent de lijst ook, maar
  alleen om het al tijdens het typen te melden.

## Draaien

Vereist: Node 20+ en de bestaande Python-venv in de projectroot.

```bash
cd web
npm install

# Ontwikkelen (client op :5173, backend op :3000)
npm run dev

# Productie op de 105
npm run build
npm start          # http://<ip-van-de-105>:3000
```

Instelbaar via omgevingsvariabelen:

| Variabele          | Standaard | Betekenis                              |
|--------------------|-----------|----------------------------------------|
| `DASHBOARD_POORT`  | `3000`    | poort van de server                    |
| `DASHBOARD_HOST`   | `0.0.0.0` | luisteradres (LAN-breed)               |
| `PYTHON`           | —         | alternatieve Python; venv gaat voor    |

Deze drie leest Node uit de omgeving, niet uit `.env` — ze staan in
`.env.example` alleen ter documentatie. Zet ze in de shell of in de
Task Scheduler-taak die `npm start` draait.

De MendriX- en e-mailinstellingen komen uit de bestaande `.env` in de
projectroot; die leest Python zelf in. Daar horen ook
`DASHBOARD_EMAIL_UITGEVINKT` en `DASHBOARD_EMAIL_DOMEINEN` bij.

## Bereikbaar via lokalist.rapport

In productie draait het dashboard op de Appserver (`192.168.4.105`) op poort 80
en is het voor iedereen op het netwerk bereikbaar via <http://lokalist.rapport>.
Daar zijn drie losse dingen voor nodig; ze staan hieronder in de volgorde waarin
je ze uitvoert.

### 1. Zelfstandig draaien (op de 105)

De server moet blijven draaien zonder ingelogde gebruiker en na een herstart van
de machine vanzelf terugkomen. Dat regelt een Task Scheduler-taak:

```powershell
# Op 192.168.4.105, elevated PowerShell
cd C:\Apps\lokalist-weekrapportage\web
npm install
npm run build

cd ..
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_dashboard_service.ps1
Start-ScheduledTask -TaskName 'lokalist-dashboard'
```

Het script controleert vooraf of poort 80 vrij is, maakt de firewallregel aan en
registreert de taak met trigger *bij het opstarten* (30 seconden vertraging),
zonder tijdslimiet en met automatische herstart na een crash.

De taak draait als `TRANSPORT\Jeroen`, **niet** als SYSTEM: het dashboard start
Python-processen die met Windows Integrated Auth naar SQL Server verbinden, en
het computeraccount `TRANSPORT\APPSERVER$` heeft geen rechten op MENDRIXDB01.

De poort staat in [`scripts/start_dashboard.cmd`](../scripts/start_dashboard.cmd);
opstartregels en Node-fouten komen in `logs/webserver.log`.

### 2. De naam

`lokalist.rapport` bestaat alleen als een DNS-server hem kent. Domein-pc's
vragen dat altijd eerst aan de domeincontroller `Domeinserver.Transport.local`
(`192.168.4.101`); die is voor `Transport.local` gezaghebbend en geeft voor een
onbekende naam meteen "bestaat niet" terug. Een tweede DNS-server in de
netwerkinstellingen wordt daarna niet meer geraadpleegd.

`.rapport` is een verzonnen topleveldomein: prima binnen het eigen netwerk, maar
het bestaat op internet niet. Daarom moet de naam altijd lokaal opgelost worden.

Kies één van deze drie:

**a. hosts-bestand op de werkplek** — geen domeinrechten nodig, alleen lokaal
admin op die machine. Prima als het om een handjevol pc's gaat (bijvoorbeeld
alleen `Werkplekken`, 192.168.4.103). Voeg als administrator deze regel toe aan
`C:\Windows\System32\drivers\etc\hosts`:

```
192.168.4.105    lokalist.rapport
```

Nadeel: per machine handmatig, en opnieuw langs bij een IP-wijziging.

Controleer met `ping lokalist.rapport` (moet `192.168.4.105` tonen), **niet** met
`nslookup`: dat vraagt het rechtstreeks aan de DNS-server en slaat het
hosts-bestand over, dus dat blijft "niet gevonden" melden terwijl de browser de
naam wel vindt.

**b. Record op de domeincontroller** — de nette oplossing: eenmalig instellen,
werkt daarna voor élke pc in het domein. Vereist een account in Domain Admins;
dat is op dit moment alleen het ingebouwde `Administrator`-account van
`Transport.local` (`TRANSPORT\jeroen` en `TRANSPORT\adm-jeroen` hebben die
rechten niet). Op de domeincontroller:

```powershell
Add-DnsServerPrimaryZone -Name "rapport" -ReplicationScope "Forest"
Add-DnsServerResourceRecordA -ZoneName "rapport" -Name "lokalist" `
    -IPv4Address 192.168.4.105
```

Wil je liever geen nieuwe zone, dan volstaat één A-record in de bestaande zone
`Transport.local`; de naam wordt dan `lokalist.transport.local`.

**c. Local DNS-record op de UniFi** (`192.168.4.245`) — de UniFi beantwoordt DNS
en jij kunt er zelf bij, maar domein-pc's stellen hun vraag aan de DC en die
stuurt onbekende namen niet naar de UniFi door. Dit werkt dus alleen als er op
de DC ook een conditional forwarder voor `rapport` naar `192.168.4.245` wordt
gezet — en daar heb je dezelfde rechten voor nodig als bij b.

Bij route b en c controleer je met `nslookup lokalist.rapport`; dat moet
`192.168.4.105` teruggeven. Bij route a werkt `nslookup` niet — zie daar.

### 3. Openen

<http://lokalist.rapport> — zonder poortnummer, want de server luistert op 80.
Chrome en Edge zien een onbekend topleveldomein soms aan voor een zoekopdracht;
typ dan één keer voluit `http://lokalist.rapport`.

Ontwikkelen op je eigen machine verandert hier niet door: `npm run dev` blijft
`localhost:3000` en `localhost:5173` gebruiken en staat volledig los van de 105.

### Een tweede webproject op poort 80

Poort 80 kan er op de Appserver maar één tegelijk hebben. Komt er later nog een
webproject dat een eigen naam wil, zet dan een reverse proxy op 80 die op
hostnaam routeert en zet dit dashboard terug op 3000 (`DASHBOARD_POORT` in
`start_dashboard.cmd`). Python-taken zoals de zondagrun gebruiken geen poort en
komen nooit in conflict.

## Testen

```bash
npm test                  # hook, modal, velden, routes, Python-brug
npx tsc --noEmit -p tsconfig.json
```

De Python-kant draait mee in de gewone suite:

```bash
pytest --cov --cov-fail-under=80
```

## Beveiliging

Er zit **geen authenticatie** op het dashboard: het is bedoeld voor het interne
netwerk van de 105. Iedereen die de poort kan bereiken, kan een verzamelorder
verwijderen en opnieuw laten genereren. Zet de server daarom niet open naar
buiten. Wil je wel afscherming, dan is dat een aparte uitbreiding.
