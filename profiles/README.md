# Profily SVJ

Profil převádí role z katalogu operací na účty konkrétního SVJ a popisuje jeho jednotky
(označení, plocha, podíl na společných částech), služby, položky správy a identifikaci.
Vedle profilu `<id>.yaml` může být předpis záloh `<id>-predpisy.yaml`.

Profil skutečného SVJ do tohoto repozitáře nepatří. Profil pilotního SVJ, na kterém se
aplikace vyvíjí, je v soukromém repozitáři `opensvj-pilot`; složku určuje `PROFILY` v
`.env`.

`ukazka.yaml` a `ukazka-predpisy.yaml` popisují vymyšlené SVJ „Ukázková 12“. Stojí na něm
testy a je výchozí, když `.env` neurčí jiný profil. Když se v něm něco změní, změní se
i ručně spočítané částky v testech.
