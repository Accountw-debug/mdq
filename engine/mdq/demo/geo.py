"""Orte für die Adressen des Demo-Mandanten.

Öffentliche Ortsangaben (Ort, Postleitzahl, Region). Die Zuordnung PLZ ↔ Ort ist
plausibel, aber kein geprüftes PLZ-Verzeichnis – die Regel AR-VAL-004 prüft in V1 nur
das **Format** gegen `logic/dictionaries/postal_code_patterns.yaml`, und genau dagegen
sind diese Werte gültig. Keine Straßen oder Hausnummern realer Unternehmen.
"""

from typing import NamedTuple


class Place(NamedTuple):
    """Ort mit Postleitzahl, Region und Land."""

    city: str
    postal_code: str
    region: str
    country: str


_DE = (
    ("Berlin", "10115", "BE"), ("Hamburg", "20095", "HH"), ("München", "80331", "BY"),
    ("Köln", "50667", "NW"), ("Frankfurt am Main", "60311", "HE"), ("Stuttgart", "70173", "BW"),
    ("Düsseldorf", "40213", "NW"), ("Leipzig", "04109", "SN"), ("Dortmund", "44135", "NW"),
    ("Essen", "45127", "NW"), ("Bremen", "28195", "HB"), ("Dresden", "01067", "SN"),
    ("Hannover", "30159", "NI"), ("Nürnberg", "90402", "BY"), ("Duisburg", "47051", "NW"),
    ("Bochum", "44787", "NW"), ("Wuppertal", "42103", "NW"), ("Bielefeld", "33602", "NW"),
    ("Bonn", "53111", "NW"), ("Münster", "48143", "NW"), ("Karlsruhe", "76133", "BW"),
    ("Mannheim", "68159", "BW"), ("Augsburg", "86150", "BY"), ("Wiesbaden", "65183", "HE"),
    ("Mönchengladbach", "41061", "NW"), ("Gelsenkirchen", "45879", "NW"),
    ("Braunschweig", "38100", "NI"), ("Kiel", "24103", "SH"), ("Chemnitz", "09111", "SN"),
    ("Aachen", "52062", "NW"), ("Halle", "06108", "ST"), ("Magdeburg", "39104", "ST"),
    ("Freiburg", "79098", "BW"), ("Krefeld", "47798", "NW"), ("Lübeck", "23552", "SH"),
    ("Oberhausen", "46045", "NW"), ("Erfurt", "99084", "TH"), ("Mainz", "55116", "RP"),
    ("Rostock", "18055", "MV"), ("Kassel", "34117", "HE"), ("Hagen", "58095", "NW"),
    ("Hamm", "59065", "NW"), ("Saarbrücken", "66111", "SL"), ("Mülheim an der Ruhr", "45468", "NW"),
    ("Potsdam", "14467", "BB"), ("Ludwigshafen am Rhein", "67059", "RP"),
    ("Oldenburg", "26122", "NI"), ("Leverkusen", "51373", "NW"), ("Osnabrück", "49074", "NI"),
    ("Solingen", "42651", "NW"), ("Heidelberg", "69117", "BW"), ("Herne", "44623", "NW"),
    ("Neuss", "41460", "NW"), ("Darmstadt", "64283", "HE"), ("Paderborn", "33098", "NW"),
    ("Regensburg", "93047", "BY"), ("Ingolstadt", "85049", "BY"), ("Würzburg", "97070", "BY"),
    ("Fürth", "90762", "BY"), ("Wolfsburg", "38440", "NI"), ("Offenbach am Main", "63065", "HE"),
    ("Ulm", "89073", "BW"), ("Heilbronn", "74072", "BW"), ("Pforzheim", "75175", "BW"),
    ("Göttingen", "37073", "NI"), ("Bottrop", "46236", "NW"), ("Trier", "54290", "RP"),
    ("Recklinghausen", "45657", "NW"), ("Reutlingen", "72764", "BW"), ("Bremerhaven", "27568", "HB"),
    ("Koblenz", "56068", "RP"), ("Bergisch Gladbach", "51465", "NW"), ("Jena", "07743", "TH"),
    ("Remscheid", "42853", "NW"), ("Erlangen", "91052", "BY"), ("Moers", "47441", "NW"),
    ("Siegen", "57072", "NW"), ("Hildesheim", "31134", "NI"), ("Salzgitter", "38226", "NI"),
    ("Cottbus", "03046", "BB"), ("Kaiserslautern", "67655", "RP"), ("Gütersloh", "33330", "NW"),
    ("Schwerin", "19053", "MV"), ("Witten", "58452", "NW"), ("Gera", "07545", "TH"),
    ("Iserlohn", "58636", "NW"), ("Ludwigsburg", "71634", "BW"), ("Hanau", "63450", "HE"),
    ("Esslingen am Neckar", "73728", "BW"), ("Zwickau", "08056", "SN"), ("Düren", "52349", "NW"),
    ("Ratingen", "40878", "NW"), ("Tübingen", "72070", "BW"), ("Flensburg", "24937", "SH"),
    ("Gießen", "35390", "HE"), ("Villingen-Schwenningen", "78050", "BW"),
    ("Konstanz", "78462", "BW"), ("Worms", "67547", "RP"), ("Marburg", "35037", "HE"),
    ("Minden", "32423", "NW"), ("Norderstedt", "22846", "SH"), ("Delmenhorst", "27749", "NI"),
    ("Bamberg", "96047", "BY"), ("Viersen", "41747", "NW"), ("Rheine", "48431", "NW"),
    ("Gladbeck", "45964", "NW"), ("Troisdorf", "53840", "NW"), ("Dorsten", "46282", "NW"),
    ("Detmold", "32756", "NW"), ("Lüneburg", "21335", "NI"), ("Bayreuth", "95444", "BY"),
    ("Castrop-Rauxel", "44575", "NW"), ("Landshut", "84028", "BY"),
    ("Brandenburg an der Havel", "14770", "BB"), ("Aschaffenburg", "63739", "BY"),
    ("Celle", "29221", "NI"), ("Kempten", "87435", "BY"), ("Fulda", "36037", "HE"),
    ("Aalen", "73430", "BW"), ("Lippstadt", "59555", "NW"), ("Dinslaken", "46535", "NW"),
    ("Herford", "32052", "NW"), ("Kerpen", "50171", "NW"), ("Plauen", "08523", "SN"),
    ("Neumünster", "24534", "SH"), ("Rosenheim", "83022", "BY"),
    ("Schwäbisch Gmünd", "73525", "BW"), ("Neubrandenburg", "17033", "MV"),
    ("Frankfurt (Oder)", "15230", "BB"), ("Görlitz", "02826", "SN"),
    ("Sindelfingen", "71063", "BW"), ("Friedrichshafen", "88045", "BW"),
    ("Offenburg", "77652", "BW"), ("Stralsund", "18439", "MV"), ("Greifswald", "17489", "MV"),
    ("Göppingen", "73033", "BW"), ("Hattingen", "45525", "NW"), ("Wesel", "46483", "NW"),
    ("Unna", "59423", "NW"), ("Waiblingen", "71332", "BW"), ("Bocholt", "46395", "NW"),
    ("Ahlen", "59227", "NW"), ("Passau", "94032", "BY"), ("Schweinfurt", "97421", "BY"),
    ("Neuwied", "56564", "RP"), ("Emden", "26721", "NI"), ("Wolfenbüttel", "38300", "NI"),
    ("Hameln", "31785", "NI"), ("Nordhorn", "48529", "NI"), ("Sankt Augustin", "53757", "NW"),
    ("Langenfeld", "40764", "NW"), ("Euskirchen", "53879", "NW"), ("Meerbusch", "40667", "NW"),
    ("Bergheim", "50126", "NW"), ("Frechen", "50226", "NW"), ("Speyer", "67346", "RP"),
    ("Weimar", "99423", "TH"), ("Baden-Baden", "76530", "BW"), ("Hof", "95028", "BY"),
    ("Coburg", "96450", "BY"), ("Amberg", "92224", "BY"), ("Straubing", "94315", "BY"),
    ("Freising", "85354", "BY"), ("Dachau", "85221", "BY"), ("Germering", "82110", "BY"),
    ("Fürstenfeldbruck", "82256", "BY"), ("Memmingen", "87700", "BY"), ("Neu-Ulm", "89231", "BY"),
    ("Kaufbeuren", "87600", "BY"), ("Ansbach", "91522", "BY"), ("Schwabach", "91126", "BY"),
    ("Erding", "85435", "BY"), ("Deggendorf", "94469", "BY"), ("Weiden", "92637", "BY"),
    ("Cuxhaven", "27472", "NI"), ("Stade", "21682", "NI"), ("Buxtehude", "21614", "NI"),
    ("Winsen", "21423", "NI"), ("Peine", "31224", "NI"), ("Goslar", "38640", "NI"),
    ("Nordenham", "26954", "NI"), ("Papenburg", "26871", "NI"), ("Meppen", "49716", "NI"),
    ("Lingen", "49808", "NI"), ("Vechta", "49377", "NI"), ("Cloppenburg", "49661", "NI"),
    ("Leer", "26789", "NI"), ("Aurich", "26603", "NI"), ("Itzehoe", "25524", "SH"),
    ("Elmshorn", "25335", "SH"), ("Pinneberg", "25421", "SH"), ("Ahrensburg", "22926", "SH"),
    ("Reinbek", "21465", "SH"), ("Husum", "25813", "SH"), ("Heide", "25746", "SH"),
    ("Rendsburg", "24768", "SH"), ("Eckernförde", "24340", "SH"), ("Wismar", "23966", "MV"),
    ("Güstrow", "18273", "MV"), ("Waren", "17192", "MV"), ("Bautzen", "02625", "SN"),
    ("Freiberg", "09599", "SN"), ("Pirna", "01796", "SN"), ("Riesa", "01587", "SN"),
    ("Meißen", "01662", "SN"), ("Döbeln", "04720", "SN"), ("Torgau", "04860", "SN"),
    ("Dessau-Roßlau", "06844", "ST"), ("Wittenberg", "06886", "ST"), ("Stendal", "39576", "ST"),
    ("Merseburg", "06217", "ST"), ("Naumburg", "06618", "ST"), ("Eisenach", "99817", "TH"),
    ("Gotha", "99867", "TH"), ("Suhl", "98527", "TH"), ("Nordhausen", "99734", "TH"),
    ("Mühlhausen", "99974", "TH"), ("Altenburg", "04600", "TH"), ("Sonneberg", "96515", "TH"),
    ("Bernburg", "06406", "ST"), ("Halberstadt", "38820", "ST"), ("Quedlinburg", "06484", "ST"),
)

_FOREIGN = (
    ("Wien", "1010", "", "AT"), ("Graz", "8010", "", "AT"), ("Linz", "4020", "", "AT"),
    ("Salzburg", "5020", "", "AT"), ("Innsbruck", "6020", "", "AT"),
    ("Klagenfurt", "9020", "", "AT"), ("Villach", "9500", "", "AT"), ("Wels", "4600", "", "AT"),
    ("Sankt Pölten", "3100", "", "AT"), ("Dornbirn", "6850", "", "AT"),
    ("Amsterdam", "1012 AB", "", "NL"), ("Rotterdam", "3011 AD", "", "NL"),
    ("Den Haag", "2511 CV", "", "NL"), ("Utrecht", "3511 LX", "", "NL"),
    ("Eindhoven", "5611 AZ", "", "NL"), ("Groningen", "9711 LM", "", "NL"),
    ("Tilburg", "5038 EA", "", "NL"), ("Almere", "1315 HR", "", "NL"),
    ("Breda", "4811 DJ", "", "NL"), ("Nijmegen", "6511 AB", "", "NL"),
    ("Paris", "75001", "", "FR"), ("Lyon", "69001", "", "FR"), ("Marseille", "13001", "", "FR"),
    ("Toulouse", "31000", "", "FR"), ("Lille", "59000", "", "FR"), ("Bordeaux", "33000", "", "FR"),
    ("Nantes", "44000", "", "FR"), ("Strasbourg", "67000", "", "FR"), ("Rennes", "35000", "", "FR"),
    ("Grenoble", "38000", "", "FR"),
    ("Milano", "20121", "", "IT"), ("Roma", "00184", "", "IT"), ("Torino", "10121", "", "IT"),
    ("Bologna", "40121", "", "IT"), ("Firenze", "50122", "", "IT"), ("Napoli", "80121", "", "IT"),
    ("Verona", "37121", "", "IT"), ("Padova", "35121", "", "IT"), ("Genova", "16121", "", "IT"),
    ("Brescia", "25121", "", "IT"),
    ("Warszawa", "00-001", "", "PL"), ("Krakow", "30-001", "", "PL"),
    ("Wroclaw", "50-001", "", "PL"), ("Poznan", "60-001", "", "PL"), ("Gdansk", "80-001", "", "PL"),
    ("Lodz", "90-001", "", "PL"), ("Katowice", "40-001", "", "PL"), ("Szczecin", "70-001", "", "PL"),
    ("Zürich", "8001", "", "CH"), ("Genf", "1201", "", "CH"), ("Basel", "4051", "", "CH"),
    ("Bern", "3011", "", "CH"), ("Lausanne", "1003", "", "CH"), ("Winterthur", "8400", "", "CH"),
    ("Luzern", "6003", "", "CH"), ("Sankt Gallen", "9000", "", "CH"),
    ("New York", "10001", "NY", "US"), ("Chicago", "60601", "IL", "US"),
    ("Houston", "77002", "TX", "US"), ("Atlanta", "30303", "GA", "US"),
    ("Boston", "02110", "MA", "US"), ("Detroit", "48226", "MI", "US"),
)

#: Deutsche Orte (~200)
GERMAN_PLACES = tuple(Place(city, plz, regio, "DE") for city, plz, regio in _DE)

#: Ausländische Orte (~60), gruppiert nach Land
FOREIGN_PLACES = tuple(Place(*entry) for entry in _FOREIGN)

ALL_PLACES = GERMAN_PLACES + FOREIGN_PLACES


def places_by_country(country: str) -> tuple[Place, ...]:
    """Alle Orte eines Landes – Reihenfolge wie in der Liste, also deterministisch."""
    return tuple(place for place in ALL_PLACES if place.country == country)
