# Groovetown Jack Snooker -tulospalvelubotti

Kaudella '23-'24 Groovessa otetaan käyttöön uusi tulospalvelubotti.

## Käyttöohje

Ottelun päätyttyä voittaja raportoi tuloksen tekstiviestillä tulospalvelu-bottiin numeroon 045 4901 *** [^1].
[^1]: kolme viimeistä numeroa = maksimi-breikki.

Em. numeroon lähetetään tekstiviesti (SMS, normaalihintainen), sisältäen tiedon pelaajista, lopputuloksen sekä mahdollinen ottelun korkein breikki. Viestin ei tarvitse noudattaa mitään tiettyä muotoa, mutta varminta on käyttää sukunimiä, esim.:

> Harju-Virta - Ahonen 2-0, breikki Harju-Virta 25.

Botti hoitaa tulosten syötön tietokantaan automaattisesti viestin perusteella. Botti kuittaa onnistuneen syötön vastausviestissä. Lohkojen reaaliaikainen tilanne tulee osallistujien nähtäväksi online-dokumenttiin, johon linkki jaetaan erikseen.

## Huomioitavaa

* Botti olettaa että ottelu kuuluu kuluvaan pelijaksoon. Jos pelijakso on ehtinyt päättyä, ei ottelun tulosta tule lähettää botille, vaan ilmoittaa erikseen ylläpidolle.
* Ratkaisu ei tällä hetkellä kontrolloi toisteisia ottelukirjauksia. Jos saman ottelun tulos lähetetään useampaan kertaan, se tallentuu tietokantaan useampaan kertaan. Ottelumääriä seurataan erikseen ylläpidon toimesta.
