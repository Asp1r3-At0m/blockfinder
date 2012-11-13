#!/usr/bin/python
import blockfinder
import unittest
import os
import shutil
from tempfile import mkdtemp
import test_data

try:
    import IPy
except ImportError:
    IPy = None


class BlockFinderTestExtras:
    def __init__(self):
        self.base_test_dir = mkdtemp()
        self.test_dir = self.base_test_dir + "/test/"
        self.block_f = blockfinder.Blockfinder(self.test_dir, "Mozilla")

    def create_new_test_cache_dir(self):
        self.block_f.create_blockfinder_cache_dir()
        self.block_f.database_cache.connect_to_database()
        self.block_f.database_cache.create_sql_database()

    def load_del_test_data(self):
        delegations = [test_data.return_sub_apnic_del()]
        rows = []
        for delegation in delegations:
            for entry in delegation:
                registry = str(entry['registry'])
                if not registry.isdigit() and str (entry['cc']) !="*":
                    temp_row = [entry['registry'], entry['cc'], entry['start'], \
                        entry['value'], entry['date'], entry['status'], entry['type']]
                    rows.append(temp_row)
        self.block_f.database_cache.insert_into_sql_database(rows)

    def load_lir_test_data(self):
        self.block_f.update_lir_delegation_cache("https://github.com/downloads/d1b/blockfinder/tiny_lir_data_for_test.gz")
        self.block_f.database_cache.create_or_replace_lir_table_in_db()
        self.block_f.extract_info_from_lir_file_and_insert_into_sqlite("tiny_lir_data_for_test")

    def copy_country_code_txt(self):
        shutil.copy(str(os.path.expanduser('~')) + "/.blockfinder/countrycodes.txt", self.block_f.cache_dir + "countrycodes.txt")

    def clean_up(self):
        shutil.rmtree(self.base_test_dir, True)

class BaseBlockfinderTest(unittest.TestCase):
    """ This is the base blockfinder test class and provides
        a setUp and a tearDown which create and destroy a temporary
        cache directory and database respectively.
    """
    def setUp(self):
        self.extra_block_test_f = BlockFinderTestExtras()
        self.block_f = blockfinder.Blockfinder(self.extra_block_test_f.test_dir, "Mozilla")
        self.extra_block_test_f.create_new_test_cache_dir()
        self.extra_block_test_f.load_del_test_data()

    def tearDown(self):
        self.extra_block_test_f.clean_up()

class CheckReverseLookup(BaseBlockfinderTest):
    ipValues = ( (3229318011, '192.123.123.123'),
            (3463778365, '206.117.16.61'),
            (4278190202, '255.0.0.122'),
            (3654084623, '217.204.232.15'),
            (134217728, '8.0.0.0'))

    rirValues = ( ('175.45.176.100', 'KP'),
                  ('193.9.26.0', 'HU'),
                  ('193.9.25.1', 'PL'),
                  ('193.9.25.255', 'PL'),
                  )
    asnValues = ( ('681', 'NZ'),
                ('173', 'JP')
                )


    def tearDown(self):
        self.extra_block_test_f.clean_up()

    def reverse_lookup_cc_matcher(self, method, values):
        self.block_f.database_cache.connect_to_database()
        self.block_f.download_country_code_file()
        for value, cc in values:
            result = method(value)
            self.assertEqual(result, cc)

    def test_rir_lookup(self):
        method = self.block_f.database_cache.rir_lookup
        self.reverse_lookup_cc_matcher(method, self.rirValues)

    def test_asn_lookup(self):
        method = self.block_f.database_cache.asn_lookup
        self.reverse_lookup_cc_matcher(method, self.asnValues)

    def test_ip_address_to_dec(self):
        for dec, ip in self.ipValues:
            result = blockfinder.ip_address_to_dec(ip)
            self.assertEqual(result, dec)

class CheckBlockFinder(BaseBlockfinderTest):
    # You can add known blocks to the tuple as a list
    # they will be looked up and checked
    known_ipv4_Results = ( ('mm', ['203.81.160.0/20', '203.81.64.0/19']),
                             ('kp', ['175.45.176.0/22']))

    def test_ipv4_bf(self):
        self.block_f.database_cache.connect_to_database()
        for cc, values in self.known_ipv4_Results:
            result = self.block_f.database_cache.use_sql_database("ipv4", cc.upper())
            self.assertEqual(result, values)
        self.block_f.database_cache.commit_and_close_database()
    def test_ipv6_bf(self):
        self.block_f.database_cache.connect_to_database()
        expected = ['2001:200:2000::/35', '2001:200:4000::/34', '2001:200:8000::/33', '2001:200::/35']
        result = self.block_f.database_cache.use_sql_database("ipv6", "JP")
        self.assertEqual(result, expected)
        self.block_f.database_cache.commit_and_close_database()

    def test_lir_fetching_and_use(self):
        """ test LIR fetching and use. """
        """ ipv4 """
        self.block_f.database_cache.connect_to_database()
        self.extra_block_test_f.load_lir_test_data()
        self.block_f.download_country_code_file()
        self.assertEqual(self.block_f.database_cache._rir_or_lir_lookup_ipv4("80.16.151.184", "LIR"), "IT")
        self.assertEqual(self.block_f.database_cache._rir_or_lir_lookup_ipv4("80.16.151.180", "LIR"), "IT")
        self.assertEqual(self.block_f.database_cache._rir_or_lir_lookup_ipv4("213.95.6.32", "LIR"), "DE")

        """ ipv6 """
        if IPy:
            self.assertEqual(self.block_f.database_cache.rir_or_lir_lookup_ipv6("2001:0658:021A::", "2001%", "LIR"), u"DE")
            self.assertEqual(self.block_f.database_cache.rir_or_lir_lookup_ipv6("2001:67c:320::", "2001%", "LIR"), u"DE")
            self.assertEqual(self.block_f.database_cache.rir_or_lir_lookup_ipv6("2001:670:0085::", "2001%", "LIR"), u"FI")
        self.block_f.database_cache.commit_and_close_database()

class CheckBasicFunctionOperation(unittest.TestCase):
    def test_calc_ipv4_subnet_boundary(self):
        for i in range(0, 29):
            host_count = 2 ** i
            subnet = 32 - i
            self.assertEqual(blockfinder.calculate_ipv4_subnet(host_count), subnet)

    def test_calc_ipv4_subnet_not_on_boundary(self):
        self.assertEqual(blockfinder.calculate_ipv4_subnet(254), 24)
        self.assertEqual(blockfinder.calculate_ipv4_subnet(255), 24)
        self.assertEqual(blockfinder.calculate_ipv4_subnet(257), 23)
        self.assertEqual(blockfinder.calculate_ipv4_subnet(259), 23)

    def test_ipv4_address_to_dec(self):
        self.assertEqual(blockfinder.ip_address_to_dec("0.0.0.0"), 0)
        self.assertEqual(blockfinder.ip_address_to_dec("4.2.2.2"), 67240450)
        self.assertEqual(blockfinder.ip_address_to_dec("217.204.232.15"), 3654084623)
        self.assertEqual(blockfinder.ip_address_to_dec("255.255.255.255"), 4294967295)

    def test_ipv4_address_to_dec_against_IPy(self):
        if IPy is not None:
            for i in range(0, 255):
                ipaddr = "%s.%s.%s.%s" % (i, i, i, i)
                self.assertEqual(blockfinder.ip_address_to_dec(ipaddr), IPy.IP(ipaddr).int())

    def test_return_first_ip_and_number_in_inetnum(self):
        line = "1.1.1.1 - 1.1.1.2"
        self.assertEqual(blockfinder.return_first_ip_and_number_in_inetnum(line), ("1.1.1.1", 2) )

if __name__ == '__main__':
    for test_class in [CheckReverseLookup, CheckBlockFinder, CheckBasicFunctionOperation]:
        unittest.TextTestRunner(verbosity=2).run(unittest.makeSuite(test_class))

