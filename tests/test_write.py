"""The IPTC-IIM fields for a Location.

Country-only Locations are not written through the CLI yet, so the rule that leaves out
Province-State and the country code is checked on the fields chosen for a Location.
"""

from nomos.location import Location
from nomos.write import iptc_tags


def test_iptc_fields_leave_out_province_state_for_a_country_only_location():
    tags = iptc_tags(Location(country="Vatican City", country_code="VA"))

    assert "IPTC:Province-State" not in tags
    assert tags["IPTC:Country-PrimaryLocationName"] == "Vatican City"
    assert tags["IPTC:Country-PrimaryLocationCode"] == "VA"


def test_iptc_fields_leave_out_the_country_code_when_there_is_none():
    tags = iptc_tags(Location(country="Falkland Islands (UK)", country_code=None))

    assert "IPTC:Country-PrimaryLocationCode" not in tags
    assert tags["IPTC:Country-PrimaryLocationName"] == "Falkland Islands (UK)"
