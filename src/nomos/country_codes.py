"""ISO 3166-1 alpha-3 to alpha-2 country codes.

A static table shipped with Nomos, generated once from the ISO 3166-1 list
(pycountry 26.2.16). The boundary dataset identifies Countries by alpha-3 code;
photo software expects alpha-2. A code not in this table gets no country code.
"""

ALPHA3_TO_ALPHA2: dict[str, str] = {
    "ABW": "AW",  # Aruba
    "AFG": "AF",  # Afghanistan
    "AGO": "AO",  # Angola
    "AIA": "AI",  # Anguilla
    "ALA": "AX",  # Åland Islands
    "ALB": "AL",  # Albania
    "AND": "AD",  # Andorra
    "ARE": "AE",  # United Arab Emirates
    "ARG": "AR",  # Argentina
    "ARM": "AM",  # Armenia
    "ASM": "AS",  # American Samoa
    "ATA": "AQ",  # Antarctica
    "ATF": "TF",  # French Southern Territories
    "ATG": "AG",  # Antigua and Barbuda
    "AUS": "AU",  # Australia
    "AUT": "AT",  # Austria
    "AZE": "AZ",  # Azerbaijan
    "BDI": "BI",  # Burundi
    "BEL": "BE",  # Belgium
    "BEN": "BJ",  # Benin
    "BES": "BQ",  # Bonaire, Sint Eustatius and Saba
    "BFA": "BF",  # Burkina Faso
    "BGD": "BD",  # Bangladesh
    "BGR": "BG",  # Bulgaria
    "BHR": "BH",  # Bahrain
    "BHS": "BS",  # Bahamas
    "BIH": "BA",  # Bosnia and Herzegovina
    "BLM": "BL",  # Saint Barthélemy
    "BLR": "BY",  # Belarus
    "BLZ": "BZ",  # Belize
    "BMU": "BM",  # Bermuda
    "BOL": "BO",  # Bolivia, Plurinational State of
    "BRA": "BR",  # Brazil
    "BRB": "BB",  # Barbados
    "BRN": "BN",  # Brunei Darussalam
    "BTN": "BT",  # Bhutan
    "BVT": "BV",  # Bouvet Island
    "BWA": "BW",  # Botswana
    "CAF": "CF",  # Central African Republic
    "CAN": "CA",  # Canada
    "CCK": "CC",  # Cocos (Keeling) Islands
    "CHE": "CH",  # Switzerland
    "CHL": "CL",  # Chile
    "CHN": "CN",  # China
    "CIV": "CI",  # Côte d'Ivoire
    "CMR": "CM",  # Cameroon
    "COD": "CD",  # Congo, The Democratic Republic of the
    "COG": "CG",  # Congo
    "COK": "CK",  # Cook Islands
    "COL": "CO",  # Colombia
    "COM": "KM",  # Comoros
    "CPV": "CV",  # Cabo Verde
    "CRI": "CR",  # Costa Rica
    "CUB": "CU",  # Cuba
    "CUW": "CW",  # Curaçao
    "CXR": "CX",  # Christmas Island
    "CYM": "KY",  # Cayman Islands
    "CYP": "CY",  # Cyprus
    "CZE": "CZ",  # Czechia
    "DEU": "DE",  # Germany
    "DJI": "DJ",  # Djibouti
    "DMA": "DM",  # Dominica
    "DNK": "DK",  # Denmark
    "DOM": "DO",  # Dominican Republic
    "DZA": "DZ",  # Algeria
    "ECU": "EC",  # Ecuador
    "EGY": "EG",  # Egypt
    "ERI": "ER",  # Eritrea
    "ESH": "EH",  # Western Sahara
    "ESP": "ES",  # Spain
    "EST": "EE",  # Estonia
    "ETH": "ET",  # Ethiopia
    "FIN": "FI",  # Finland
    "FJI": "FJ",  # Fiji
    "FLK": "FK",  # Falkland Islands (Malvinas)
    "FRA": "FR",  # France
    "FRO": "FO",  # Faroe Islands
    "FSM": "FM",  # Micronesia, Federated States of
    "GAB": "GA",  # Gabon
    "GBR": "GB",  # United Kingdom
    "GEO": "GE",  # Georgia
    "GGY": "GG",  # Guernsey
    "GHA": "GH",  # Ghana
    "GIB": "GI",  # Gibraltar
    "GIN": "GN",  # Guinea
    "GLP": "GP",  # Guadeloupe
    "GMB": "GM",  # Gambia
    "GNB": "GW",  # Guinea-Bissau
    "GNQ": "GQ",  # Equatorial Guinea
    "GRC": "GR",  # Greece
    "GRD": "GD",  # Grenada
    "GRL": "GL",  # Greenland
    "GTM": "GT",  # Guatemala
    "GUF": "GF",  # French Guiana
    "GUM": "GU",  # Guam
    "GUY": "GY",  # Guyana
    "HKG": "HK",  # Hong Kong
    "HMD": "HM",  # Heard Island and McDonald Islands
    "HND": "HN",  # Honduras
    "HRV": "HR",  # Croatia
    "HTI": "HT",  # Haiti
    "HUN": "HU",  # Hungary
    "IDN": "ID",  # Indonesia
    "IMN": "IM",  # Isle of Man
    "IND": "IN",  # India
    "IOT": "IO",  # British Indian Ocean Territory
    "IRL": "IE",  # Ireland
    "IRN": "IR",  # Iran, Islamic Republic of
    "IRQ": "IQ",  # Iraq
    "ISL": "IS",  # Iceland
    "ISR": "IL",  # Israel
    "ITA": "IT",  # Italy
    "JAM": "JM",  # Jamaica
    "JEY": "JE",  # Jersey
    "JOR": "JO",  # Jordan
    "JPN": "JP",  # Japan
    "KAZ": "KZ",  # Kazakhstan
    "KEN": "KE",  # Kenya
    "KGZ": "KG",  # Kyrgyzstan
    "KHM": "KH",  # Cambodia
    "KIR": "KI",  # Kiribati
    "KNA": "KN",  # Saint Kitts and Nevis
    "KOR": "KR",  # Korea, Republic of
    "KWT": "KW",  # Kuwait
    "LAO": "LA",  # Lao People's Democratic Republic
    "LBN": "LB",  # Lebanon
    "LBR": "LR",  # Liberia
    "LBY": "LY",  # Libya
    "LCA": "LC",  # Saint Lucia
    "LIE": "LI",  # Liechtenstein
    "LKA": "LK",  # Sri Lanka
    "LSO": "LS",  # Lesotho
    "LTU": "LT",  # Lithuania
    "LUX": "LU",  # Luxembourg
    "LVA": "LV",  # Latvia
    "MAC": "MO",  # Macao
    "MAF": "MF",  # Saint Martin (French part)
    "MAR": "MA",  # Morocco
    "MCO": "MC",  # Monaco
    "MDA": "MD",  # Moldova, Republic of
    "MDG": "MG",  # Madagascar
    "MDV": "MV",  # Maldives
    "MEX": "MX",  # Mexico
    "MHL": "MH",  # Marshall Islands
    "MKD": "MK",  # North Macedonia
    "MLI": "ML",  # Mali
    "MLT": "MT",  # Malta
    "MMR": "MM",  # Myanmar
    "MNE": "ME",  # Montenegro
    "MNG": "MN",  # Mongolia
    "MNP": "MP",  # Northern Mariana Islands
    "MOZ": "MZ",  # Mozambique
    "MRT": "MR",  # Mauritania
    "MSR": "MS",  # Montserrat
    "MTQ": "MQ",  # Martinique
    "MUS": "MU",  # Mauritius
    "MWI": "MW",  # Malawi
    "MYS": "MY",  # Malaysia
    "MYT": "YT",  # Mayotte
    "NAM": "NA",  # Namibia
    "NCL": "NC",  # New Caledonia
    "NER": "NE",  # Niger
    "NFK": "NF",  # Norfolk Island
    "NGA": "NG",  # Nigeria
    "NIC": "NI",  # Nicaragua
    "NIU": "NU",  # Niue
    "NLD": "NL",  # Netherlands
    "NOR": "NO",  # Norway
    "NPL": "NP",  # Nepal
    "NRU": "NR",  # Nauru
    "NZL": "NZ",  # New Zealand
    "OMN": "OM",  # Oman
    "PAK": "PK",  # Pakistan
    "PAN": "PA",  # Panama
    "PCN": "PN",  # Pitcairn
    "PER": "PE",  # Peru
    "PHL": "PH",  # Philippines
    "PLW": "PW",  # Palau
    "PNG": "PG",  # Papua New Guinea
    "POL": "PL",  # Poland
    "PRI": "PR",  # Puerto Rico
    "PRK": "KP",  # Korea, Democratic People's Republic of
    "PRT": "PT",  # Portugal
    "PRY": "PY",  # Paraguay
    "PSE": "PS",  # Palestine, State of
    "PYF": "PF",  # French Polynesia
    "QAT": "QA",  # Qatar
    "REU": "RE",  # Réunion
    "ROU": "RO",  # Romania
    "RUS": "RU",  # Russian Federation
    "RWA": "RW",  # Rwanda
    "SAU": "SA",  # Saudi Arabia
    "SDN": "SD",  # Sudan
    "SEN": "SN",  # Senegal
    "SGP": "SG",  # Singapore
    "SGS": "GS",  # South Georgia and the South Sandwich Islands
    "SHN": "SH",  # Saint Helena, Ascension and Tristan da Cunha
    "SJM": "SJ",  # Svalbard and Jan Mayen
    "SLB": "SB",  # Solomon Islands
    "SLE": "SL",  # Sierra Leone
    "SLV": "SV",  # El Salvador
    "SMR": "SM",  # San Marino
    "SOM": "SO",  # Somalia
    "SPM": "PM",  # Saint Pierre and Miquelon
    "SRB": "RS",  # Serbia
    "SSD": "SS",  # South Sudan
    "STP": "ST",  # Sao Tome and Principe
    "SUR": "SR",  # Suriname
    "SVK": "SK",  # Slovakia
    "SVN": "SI",  # Slovenia
    "SWE": "SE",  # Sweden
    "SWZ": "SZ",  # Eswatini
    "SXM": "SX",  # Sint Maarten (Dutch part)
    "SYC": "SC",  # Seychelles
    "SYR": "SY",  # Syrian Arab Republic
    "TCA": "TC",  # Turks and Caicos Islands
    "TCD": "TD",  # Chad
    "TGO": "TG",  # Togo
    "THA": "TH",  # Thailand
    "TJK": "TJ",  # Tajikistan
    "TKL": "TK",  # Tokelau
    "TKM": "TM",  # Turkmenistan
    "TLS": "TL",  # Timor-Leste
    "TON": "TO",  # Tonga
    "TTO": "TT",  # Trinidad and Tobago
    "TUN": "TN",  # Tunisia
    "TUR": "TR",  # Türkiye
    "TUV": "TV",  # Tuvalu
    "TWN": "TW",  # Taiwan, Province of China
    "TZA": "TZ",  # Tanzania, United Republic of
    "UGA": "UG",  # Uganda
    "UKR": "UA",  # Ukraine
    "UMI": "UM",  # United States Minor Outlying Islands
    "URY": "UY",  # Uruguay
    "USA": "US",  # United States
    "UZB": "UZ",  # Uzbekistan
    "VAT": "VA",  # Holy See (Vatican City State)
    "VCT": "VC",  # Saint Vincent and the Grenadines
    "VEN": "VE",  # Venezuela, Bolivarian Republic of
    "VGB": "VG",  # Virgin Islands, British
    "VIR": "VI",  # Virgin Islands, U.S.
    "VNM": "VN",  # Viet Nam
    "VUT": "VU",  # Vanuatu
    "WLF": "WF",  # Wallis and Futuna
    "WSM": "WS",  # Samoa
    "YEM": "YE",  # Yemen
    "ZAF": "ZA",  # South Africa
    "ZMB": "ZM",  # Zambia
    "ZWE": "ZW",  # Zimbabwe
}


def alpha2_for(alpha3: str) -> str | None:
    """Return the alpha-2 code for an alpha-3 code, or None if it is not in the table."""
    return ALPHA3_TO_ALPHA2.get(alpha3.upper())
