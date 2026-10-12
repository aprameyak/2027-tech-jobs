import unittest

from normalize_locations import clean_location, is_clean, normalize_location


class NormalizeLocationTests(unittest.TestCase):
    def check(self, raw, expected):
        value, ok = normalize_location(raw)
        self.assertTrue(ok, raw)
        self.assertEqual(value, expected, raw)
        self.assertTrue(is_clean(value), raw)

    def test_aliases(self):
        self.check('NYC', 'New York, NY')
        self.check('New York City, NY', 'New York, NY')
        self.check('SF', 'San Francisco, CA')
        self.check('LA', 'Los Angeles, CA')
        self.check('Hub - San Francisco', 'San Francisco, CA')

    def test_country_prefixes_and_suffixes(self):
        self.check('US - Denver, CO', 'Denver, CO')
        self.check('USA - New York - Malta', 'Malta, NY')
        self.check('US, WA, Seattle', 'Seattle, WA')
        self.check('Ashburn, VA, US', 'Ashburn, VA')
        self.check('Toronto, ON, CAN', 'Toronto, ON')
        self.check('CA, BC, Vancouver', 'Vancouver, BC')
        self.check('United States-Utah-Roy', 'Roy, UT')

    def test_city_named_like_a_state(self):
        self.check('Washington, DC', 'Washington, DC')
        self.check('Delaware, OH', 'Delaware, OH')
        self.check('Wyoming, MI', 'Wyoming, MI')
        self.check('New Brunswick, NJ', 'New Brunswick, NJ')

    def test_nebraska_is_not_a_street_direction(self):
        self.check('Omaha, NE; San Jose, CA', 'Omaha, NE; San Jose, CA')

    def test_glued_locations_are_split(self):
        self.check('Minneapolis, MNDenver, CO', 'Minneapolis, MN; Denver, CO')
        self.check('Menlo Park, CANYC', 'Menlo Park, CA; New York, NY')
        self.check('Seattle, WASFNYC', 'Seattle, WA; San Francisco, CA; New York, NY')
        self.check('Toronto, ON, CanadaWaterloo, ON', 'Toronto, ON; Waterloo, ON')
        self.check('Waterloo, ONT, Canada', 'Waterloo, ON')

    def test_state_oregon_is_not_the_word_or(self):
        self.check(
            '5 locationsAustin, TXSanta Clara, CAHillsboro, ORFolsom, CAPhoenix, AZ',
            'Austin, TX; Santa Clara, CA; Hillsboro, OR; Folsom, CA; Phoenix, AZ',
        )

    def test_noise_is_removed(self):
        self.check('Boise, ID - Main Site', 'Boise, ID')
        self.check('Dallas, TX - Headquarters', 'Dallas, TX')
        self.check('Chicago Office', 'Chicago, IL')
        self.check('Hybrid - San Francisco, CA', 'San Francisco, CA')
        self.check('Corporate - Baton Rouge, LA', 'Baton Rouge, LA')
        self.check('Cincinnati, OH (USA)', 'Cincinnati, OH')

    def test_plant_style_addresses(self):
        self.check('CEDAR RAPIDS-131 ~ 5450 C Ave NE ~ BLDG 131, IA', 'Cedar Rapids, IA')
        self.check('HOUSTON-2001 RANKIN ROAD, TX', 'Houston, TX')
        self.check('FT WAYNE-150A ~ 1010 Production Rd ~ BLDG 150A, IN', 'Fort Wayne, IN')

    def test_street_addresses(self):
        self.check('500 Lake Shore Blvd W, Toronto, ON', 'Toronto, ON')
        self.check('Arlington County, Arlington, VA', 'Arlington, VA')

    def test_remote(self):
        self.check('Remote', 'Remote (US)')
        self.check('United States', 'Remote (US)')
        self.check('Remote - Minnesota', 'Remote (US)')
        self.check('Canada', 'Remote (Canada)')
        self.check('Remote (Canada)', 'Remote (Canada)')

    def test_uk_is_valid(self):
        self.check('London, UK', 'London, UK')
        self.assertTrue(is_clean('Glasgow, UK'))

    def test_already_clean_values_are_unchanged(self):
        for value in ('Winston-Salem, NC', 'San Francisco, CA; New York, NY', 'Remote (US)'):
            self.check(value, value)

    def test_idempotent(self):
        for raw in ('NYC', 'Menlo Park, CANYC', 'USA - New York - Malta', 'CEDAR RAPIDS-1 ~ x ~ y, IA'):
            once, _ = normalize_location(raw)
            twice, _ = normalize_location(once)
            self.assertEqual(once, twice, raw)

    def test_unresolvable_values_are_not_rewritten(self):
        for raw in ('Texas', 'Multiple Locations', 'Unknown', 'Houston, TX or San Francisco Bay Area'):
            value, ok = normalize_location(raw)
            self.assertFalse(ok and is_clean(value), raw)
            self.assertEqual(clean_location(raw), raw)


if __name__ == '__main__':
    unittest.main()
