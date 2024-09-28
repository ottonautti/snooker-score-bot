# Groovetown Jack Snooker -tulospalvelubotti

Kaudella '23-'24 Grooven Snooker-liigassa otettiin käyttöön uusi tulospalvelubotti.

## Käyttöohje

Ottelun päätyttyä voittaja raportoi tuloksen tekstiviestillä tulospalvelu-bottiin numeroon 045 4901 *** [^1].
[^1]: kolme viimeistä numeroa = snookerin maksimi-breikki.

Em. numeroon lähetetään tekstiviesti (SMS, normaalihintainen), sisältäen tiedon pelaajista, lopputuloksen sekä mahdolliset tilastobreikit. Viestin ei tarvitse noudattaa mitään tiettyä muotoa, mutta varminta on käyttää sukunimiä, esim.:

> Harju-Virta - Ahonen 2-0

tai

> Harju-Virta - Ahonen 2-0. Breikit Harju-Virta 32, Ahonen 25.

Botti hoitaa tulosten syötön tietokantaan automaattisesti viestin perusteella. Botti kuittaa onnistuneen syötön vastausviestissä. Osallistujille annetaan pääsy Google Sheets -dokumenttiin, josta voi nähdä sarjan reaaliaikaisen tilanteen.

## Huomioitavaa

* Botti olettaa että ottelu on pelattu viestin lähetyspäivänä. Jos pelijakso on ehtinyt päättyä, ei ottelun tulosta tule lähettää botille, vaan ilmoittaa erikseen ylläpidolle.
* Ratkaisu ei tällä hetkellä tunnista toisteisia ottelukirjauksia. Jos saman ottelun tulos lähetetään useampaan kertaan, se tallentuu tietokantaan useampaan kertaan.
