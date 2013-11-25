from __future__ import print_function

import os
import re
import warnings

try:
    from importlib import import_module
except ImportError:
    import_module = __import__

from distutils.version import LooseVersion

import nose

import numpy as np
from numpy.random import rand
from numpy.testing.decorators import slow

from pandas import (DataFrame, MultiIndex, read_csv, Timestamp, Index,
                    date_range, Series)
from pandas.compat import map, zip, StringIO, string_types
from pandas.io.common import URLError, urlopen, file_path_to_url
from pandas.io.html import read_html

import pandas.util.testing as tm
from pandas.util.testing import makeCustomDataframe as mkdf, network


def _have_module(module_name):
    try:
        import_module(module_name)
        return True
    except ImportError:
        return False


def _skip_if_no(module_name):
    if not _have_module(module_name):
        raise nose.SkipTest("{0!r} not found".format(module_name))


def _skip_if_none_of(module_names):
    if isinstance(module_names, string_types):
        _skip_if_no(module_names)
        if module_names == 'bs4':
            import bs4
            if bs4.__version__ == LooseVersion('4.2.0'):
                raise nose.SkipTest("Bad version of bs4: 4.2.0")
    else:
        not_found = [module_name for module_name in module_names if not
                     _have_module(module_name)]
        if set(not_found) & set(module_names):
            raise nose.SkipTest("{0!r} not found".format(not_found))
        if 'bs4' in module_names:
            import bs4
            if bs4.__version__ == LooseVersion('4.2.0'):
                raise nose.SkipTest("Bad version of bs4: 4.2.0")


DATA_PATH = tm.get_data_path()


def assert_framelist_equal(list1, list2, *args, **kwargs):
    assert len(list1) == len(list2), ('lists are not of equal size '
                                      'len(list1) == {0}, '
                                      'len(list2) == {1}'.format(len(list1),
                                                                 len(list2)))
    msg = 'not all list elements are DataFrames'
    both_frames = all(map(lambda x, y: isinstance(x, DataFrame) and
                          isinstance(y, DataFrame), list1, list2))
    assert both_frames, msg
    for frame_i, frame_j in zip(list1, list2):
        tm.assert_frame_equal(frame_i, frame_j, *args, **kwargs)
        assert not frame_i.empty, 'frames are both empty'


def test_bs4_version_fails():
    _skip_if_none_of(('bs4', 'html5lib'))
    import bs4
    if bs4.__version__ == LooseVersion('4.2.0'):
        tm.assert_raises(AssertionError, read_html, os.path.join(DATA_PATH,
                                                                 "spam.html"),
                         flavor='bs4')


class TestReadHtml(tm.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestReadHtml, cls).setupClass()
        _skip_if_none_of(('bs4', 'html5lib'))

    def read_html(self, *args, **kwargs):
        kwargs['flavor'] = kwargs.get('flavor', self.flavor)
        return read_html(*args, **kwargs)

    def setup_data(self):
        self.spam_data = os.path.join(DATA_PATH, 'spam.html')
        self.banklist_data = os.path.join(DATA_PATH, 'banklist.html')

    def setup_flavor(self):
        self.flavor = 'bs4'

    def setUp(self):
        self.setup_data()
        self.setup_flavor()

    def test_to_html_compat(self):
        df = mkdf(4, 3, data_gen_f=lambda *args: rand(), c_idx_names=False,
                  r_idx_names=False).applymap('{0:.3f}'.format).astype(float)
        out = df.to_html()
        res = self.read_html(out, attrs={'class': 'dataframe'},
                                 index_col=0)[0]
        tm.assert_frame_equal(res, df)

    @network
    def test_banklist_url(self):
        url = 'http://www.fdic.gov/bank/individual/failed/banklist.html'
        df1 = self.read_html(url, 'First Federal Bank of Florida',
                                 attrs={"id": 'table'})
        df2 = self.read_html(url, 'Metcalf Bank', attrs={'id': 'table'})

        assert_framelist_equal(df1, df2)

    @network
    def test_spam_url(self):
        url = ('http://ndb.nal.usda.gov/ndb/foods/show/1732?fg=&man=&'
               'lfacet=&format=&count=&max=25&offset=&sort=&qlookup=spam')
        df1 = self.read_html(url, '.*Water.*')
        df2 = self.read_html(url, 'Unit')

        assert_framelist_equal(df1, df2)

    @slow
    def test_banklist(self):
        df1 = self.read_html(self.banklist_data, '.*Florida.*',
                                 attrs={'id': 'table'})
        df2 = self.read_html(self.banklist_data, 'Metcalf Bank',
                                 attrs={'id': 'table'})

        assert_framelist_equal(df1, df2)

    def test_spam_no_types(self):
        with tm.assert_produces_warning(FutureWarning):
            df1 = self.read_html(self.spam_data, '.*Water.*',
                                     infer_types=False)
        with tm.assert_produces_warning(FutureWarning):
            df2 = self.read_html(self.spam_data, 'Unit', infer_types=False)

        assert_framelist_equal(df1, df2)

        self.assertEqual(df1[0].ix[0, 0], 'Proximates')
        self.assertEqual(df1[0].columns[0], 'Nutrient')

    def test_spam_with_types(self):
        df1 = self.read_html(self.spam_data, '.*Water.*')
        df2 = self.read_html(self.spam_data, 'Unit')
        assert_framelist_equal(df1, df2)

        self.assertEqual(df1[0].ix[0, 0], 'Proximates')
        self.assertEqual(df1[0].columns[0], 'Nutrient')

    def test_spam_no_match(self):
        dfs = self.read_html(self.spam_data)
        for df in dfs:
            tm.assert_isinstance(df, DataFrame)

    def test_banklist_no_match(self):
        dfs = self.read_html(self.banklist_data, attrs={'id': 'table'})
        for df in dfs:
            tm.assert_isinstance(df, DataFrame)

    def test_spam_header(self):
        df = self.read_html(self.spam_data, '.*Water.*', header=1)[0]
        self.assertEqual(df.columns[0], 'Proximates')
        self.assertFalse(df.empty)

    def test_skiprows_int(self):
        df1 = self.read_html(self.spam_data, '.*Water.*', skiprows=1)
        df2 = self.read_html(self.spam_data, 'Unit', skiprows=1)

        assert_framelist_equal(df1, df2)

    def test_skiprows_xrange(self):
        df1 = self.read_html(self.spam_data, '.*Water.*',
                                 skiprows=range(2))[0]
        df2 = self.read_html(self.spam_data, 'Unit', skiprows=range(2))[0]
        tm.assert_frame_equal(df1, df2)

    def test_skiprows_list(self):
        df1 = self.read_html(self.spam_data, '.*Water.*', skiprows=[1, 2])
        df2 = self.read_html(self.spam_data, 'Unit', skiprows=[2, 1])

        assert_framelist_equal(df1, df2)

    def test_skiprows_set(self):
        df1 = self.read_html(self.spam_data, '.*Water.*',
                                 skiprows=set([1, 2]))
        df2 = self.read_html(self.spam_data, 'Unit', skiprows=set([2, 1]))

        assert_framelist_equal(df1, df2)

    def test_skiprows_slice(self):
        df1 = self.read_html(self.spam_data, '.*Water.*', skiprows=1)
        df2 = self.read_html(self.spam_data, 'Unit', skiprows=1)

        assert_framelist_equal(df1, df2)

    def test_skiprows_slice_short(self):
        df1 = self.read_html(self.spam_data, '.*Water.*',
                                 skiprows=slice(2))
        df2 = self.read_html(self.spam_data, 'Unit', skiprows=slice(2))

        assert_framelist_equal(df1, df2)

    def test_skiprows_slice_long(self):
        df1 = self.read_html(self.spam_data, '.*Water.*',
                                 skiprows=slice(2, 5))
        df2 = self.read_html(self.spam_data, 'Unit',
                                 skiprows=slice(4, 1, -1))

        assert_framelist_equal(df1, df2)

    def test_skiprows_ndarray(self):
        df1 = self.read_html(self.spam_data, '.*Water.*',
                                 skiprows=np.arange(2))
        df2 = self.read_html(self.spam_data, 'Unit', skiprows=np.arange(2))

        assert_framelist_equal(df1, df2)

    def test_skiprows_invalid(self):
        with tm.assertRaisesRegexp(TypeError,
                                   'is not a valid type for skipping rows'):
            self.read_html(self.spam_data, '.*Water.*', skiprows='asdf')

    def test_index(self):
        df1 = self.read_html(self.spam_data, '.*Water.*', index_col=0)
        df2 = self.read_html(self.spam_data, 'Unit', index_col=0)
        assert_framelist_equal(df1, df2)

    def test_header_and_index_no_types(self):
        with tm.assert_produces_warning(FutureWarning):
            df1 = self.read_html(self.spam_data, '.*Water.*', header=1,
                                     index_col=0, infer_types=False)
        with tm.assert_produces_warning(FutureWarning):
            df2 = self.read_html(self.spam_data, 'Unit', header=1,
                                    index_col=0, infer_types=False)
        assert_framelist_equal(df1, df2)

    def test_header_and_index_with_types(self):
        df1 = self.read_html(self.spam_data, '.*Water.*', header=1,
                                 index_col=0)
        df2 = self.read_html(self.spam_data, 'Unit', header=1, index_col=0)
        assert_framelist_equal(df1, df2)

    def test_infer_types(self):
        with tm.assert_produces_warning(FutureWarning):
            df1 = self.read_html(self.spam_data, '.*Water.*', index_col=0,
                                     infer_types=False)
        with tm.assert_produces_warning(FutureWarning):
            df2 = self.read_html(self.spam_data, 'Unit', index_col=0,
                                    infer_types=False)
        assert_framelist_equal(df1, df2)

        with tm.assert_produces_warning(FutureWarning):
            df2 = self.read_html(self.spam_data, 'Unit', index_col=0,
                                    infer_types=True)

        with tm.assertRaises(AssertionError):
            assert_framelist_equal(df1, df2)

    def test_string_io(self):
        with open(self.spam_data) as f:
            data1 = StringIO(f.read())

        with open(self.spam_data) as f:
            data2 = StringIO(f.read())

        df1 = self.read_html(data1, '.*Water.*')
        df2 = self.read_html(data2, 'Unit')
        assert_framelist_equal(df1, df2)

    def test_string(self):
        with open(self.spam_data) as f:
            data = f.read()

        df1 = self.read_html(data, '.*Water.*')
        df2 = self.read_html(data, 'Unit')

        assert_framelist_equal(df1, df2)

    def test_file_like(self):
        with open(self.spam_data) as f:
            df1 = self.read_html(f, '.*Water.*')

        with open(self.spam_data) as f:
            df2 = self.read_html(f, 'Unit')

        assert_framelist_equal(df1, df2)

    @network
    def test_bad_url_protocol(self):
        with tm.assertRaises(URLError):
            self.read_html('git://github.com', match='.*Water.*')

    @network
    def test_invalid_url(self):
        with tm.assertRaises(URLError):
            self.read_html('http://www.a23950sdfa908sd.com', match='.*Water.*')

    @slow
    def test_file_url(self):
        url = self.banklist_data
        dfs = self.read_html(file_path_to_url(url), 'First', attrs={'id': 'table'})
        tm.assert_isinstance(dfs, list)
        for df in dfs:
            tm.assert_isinstance(df, DataFrame)

    @slow
    def test_invalid_table_attrs(self):
        url = self.banklist_data
        with tm.assertRaisesRegexp(ValueError, 'No tables found'):
            self.read_html(url, 'First Federal Bank of Florida',
                           attrs={'id': 'tasdfable'})

    def _bank_data(self, *args, **kwargs):
        return self.read_html(self.banklist_data, 'Metcalf',
                              attrs={'id': 'table'}, *args, **kwargs)

    @slow
    def test_multiindex_header(self):
        df = self._bank_data(header=[0, 1])[0]
        tm.assert_isinstance(df.columns, MultiIndex)

    @slow
    def test_multiindex_index(self):
        df = self._bank_data(index_col=[0, 1])[0]
        tm.assert_isinstance(df.index, MultiIndex)

    @slow
    def test_multiindex_header_index(self):
        df = self._bank_data(header=[0, 1], index_col=[0, 1])[0]
        tm.assert_isinstance(df.columns, MultiIndex)
        tm.assert_isinstance(df.index, MultiIndex)

    @slow
    def test_multiindex_header_skiprows_tuples(self):
        df = self._bank_data(header=[0, 1], skiprows=1, tupleize_cols=True)[0]
        tm.assert_isinstance(df.columns, Index)

    @slow
    def test_multiindex_header_skiprows(self):
        df = self._bank_data(header=[0, 1], skiprows=1)[0]
        tm.assert_isinstance(df.columns, MultiIndex)

    @slow
    def test_multiindex_header_index_skiprows(self):
        df = self._bank_data(header=[0, 1], index_col=[0, 1], skiprows=1)[0]
        tm.assert_isinstance(df.index, MultiIndex)
        tm.assert_isinstance(df.columns, MultiIndex)

    @slow
    def test_regex_idempotency(self):
        url = self.banklist_data
        dfs = self.read_html(file_path_to_url(url),
                                 match=re.compile(re.compile('Florida')),
                                 attrs={'id': 'table'})
        tm.assert_isinstance(dfs, list)
        for df in dfs:
            tm.assert_isinstance(df, DataFrame)

    def test_negative_skiprows(self):
        with tm.assertRaisesRegexp(ValueError,
                                   '\(you passed a negative value\)'):
            self.read_html(self.spam_data, 'Water', skiprows=-1)

    @network
    def test_multiple_matches(self):
        url = 'http://code.google.com/p/pythonxy/wiki/StandardPlugins'
        dfs = self.read_html(url, match='Python',
                                 attrs={'class': 'wikitable'})
        self.assert_(len(dfs) > 1)

    @network
    def test_pythonxy_plugins_table(self):
        url = 'http://code.google.com/p/pythonxy/wiki/StandardPlugins'
        dfs = self.read_html(url, match='Python',
                                 attrs={'class': 'wikitable'})
        zz = [df.iloc[0, 0] for df in dfs]
        self.assertEqual(sorted(zz), sorted(['Python', 'SciTE']))

    @slow
    def test_thousands_macau_stats(self):
        all_non_nan_table_index = -2
        macau_data = os.path.join(DATA_PATH, 'macau.html')
        dfs = self.read_html(macau_data, index_col=0,
                             attrs={'class': 'style1'})
        df = dfs[all_non_nan_table_index]

        self.assertFalse(any(s.isnull().any() for _, s in df.iteritems()))

    @slow
    def test_thousands_macau_index_col(self):
        all_non_nan_table_index = -2
        macau_data = os.path.join(DATA_PATH, 'macau.html')
        dfs = self.read_html(macau_data, index_col=0, header=0)
        df = dfs[all_non_nan_table_index]

        self.assertFalse(any(s.isnull().any() for _, s in df.iteritems()))

    def test_countries_municipalities(self):
        # GH5048
        data1 = StringIO('''<table>
            <thead>
                <tr>
                    <th>Country</th>
                    <th>Municipality</th>
                    <th>Year</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Ukraine</td>
                    <th>Odessa</th>
                    <td>1944</td>
                </tr>
            </tbody>
        </table>''')
        data2 = StringIO('''
        <table>
            <tbody>
                <tr>
                    <th>Country</th>
                    <th>Municipality</th>
                    <th>Year</th>
                </tr>
                <tr>
                    <td>Ukraine</td>
                    <th>Odessa</th>
                    <td>1944</td>
                </tr>
            </tbody>
        </table>''')
        res1 = self.read_html(data1)
        res2 = self.read_html(data2, header=0)
        assert_framelist_equal(res1, res2)

    def test_nyse_wsj_commas_table(self):
        data = os.path.join(DATA_PATH, 'nyse_wsj.html')
        df = self.read_html(data, index_col=0, header=0,
                            attrs={'class': 'mdcTable'})[0]

        columns = Index(['Issue(Roll over for charts and headlines)',
                         'Volume', 'Price', 'Chg', '% Chg'])
        nrows = 100
        self.assertEqual(df.shape[0], nrows)
        self.assertTrue(df.columns.equals(columns))

    @slow
    def test_banklist_header(self):
        from pandas.io.html import _remove_whitespace

        def try_remove_ws(x):
            try:
                return _remove_whitespace(x)
            except AttributeError:
                return x

        df = self.read_html(self.banklist_data, 'Metcalf',
                                attrs={'id': 'table'})[0]
        ground_truth = read_csv(os.path.join(DATA_PATH, 'banklist.csv'),
                                converters={'Updated Date': Timestamp,
                                            'Closing Date': Timestamp})
        self.assertEqual(df.shape, ground_truth.shape)
        old = ['First Vietnamese American BankIn Vietnamese',
               'Westernbank Puerto RicoEn Espanol',
               'R-G Premier Bank of Puerto RicoEn Espanol',
               'EurobankEn Espanol', 'Sanderson State BankEn Espanol',
               'Washington Mutual Bank(Including its subsidiary Washington '
               'Mutual Bank FSB)',
               'Silver State BankEn Espanol',
               'AmTrade International BankEn Espanol',
               'Hamilton Bank, NAEn Espanol',
               'The Citizens Savings BankPioneer Community Bank, Inc.']
        new = ['First Vietnamese American Bank', 'Westernbank Puerto Rico',
               'R-G Premier Bank of Puerto Rico', 'Eurobank',
               'Sanderson State Bank', 'Washington Mutual Bank',
               'Silver State Bank', 'AmTrade International Bank',
               'Hamilton Bank, NA', 'The Citizens Savings Bank']
        dfnew = df.applymap(try_remove_ws).replace(old, new)
        gtnew = ground_truth.applymap(try_remove_ws)
        converted = dfnew.convert_objects(convert_numeric=True)
        tm.assert_frame_equal(converted.convert_objects(convert_dates='coerce'),
                              gtnew)

    @slow
    def test_gold_canyon(self):
        gc = 'Gold Canyon'
        with open(self.banklist_data, 'r') as f:
            raw_text = f.read()

        self.assert_(gc in raw_text)
        df = self.read_html(self.banklist_data, 'Gold Canyon',
                                attrs={'id': 'table'})[0]
        self.assert_(gc in df.to_string())

    def test_different_number_of_rows(self):
        expected = """<table border="1" class="dataframe">
                        <thead>
                            <tr style="text-align: right;">
                            <th></th>
                            <th>C_l0_g0</th>
                            <th>C_l0_g1</th>
                            <th>C_l0_g2</th>
                            <th>C_l0_g3</th>
                            <th>C_l0_g4</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                            <th>R_l0_g0</th>
                            <td> 0.763</td>
                            <td> 0.233</td>
                            <td> nan</td>
                            <td> nan</td>
                            <td> nan</td>
                            </tr>
                            <tr>
                            <th>R_l0_g1</th>
                            <td> 0.244</td>
                            <td> 0.285</td>
                            <td> 0.392</td>
                            <td> 0.137</td>
                            <td> 0.222</td>
                            </tr>
                        </tbody>
                    </table>"""
        out = """<table border="1" class="dataframe">
                    <thead>
                        <tr style="text-align: right;">
                        <th></th>
                        <th>C_l0_g0</th>
                        <th>C_l0_g1</th>
                        <th>C_l0_g2</th>
                        <th>C_l0_g3</th>
                        <th>C_l0_g4</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                        <th>R_l0_g0</th>
                        <td> 0.763</td>
                        <td> 0.233</td>
                        </tr>
                        <tr>
                        <th>R_l0_g1</th>
                        <td> 0.244</td>
                        <td> 0.285</td>
                        <td> 0.392</td>
                        <td> 0.137</td>
                        <td> 0.222</td>
                        </tr>
                    </tbody>
                 </table>"""
        expected = self.read_html(expected, index_col=0)[0]
        res = self.read_html(out, index_col=0)[0]
        tm.assert_frame_equal(expected, res)

    def test_parse_dates_list(self):
        df = DataFrame({'date': date_range('1/1/2001', periods=10)})
        expected = df.to_html()
        res = self.read_html(expected, parse_dates=[0], index_col=0)
        tm.assert_frame_equal(df, res[0])

    def test_parse_dates_combine(self):
        raw_dates = Series(date_range('1/1/2001', periods=10))
        df = DataFrame({'date': raw_dates.map(lambda x: str(x.date())),
                        'time': raw_dates.map(lambda x: str(x.time()))})
        res = self.read_html(df.to_html(), parse_dates={'datetime': [1, 2]},
                             index_col=1)
        newdf = DataFrame({'datetime': raw_dates})
        tm.assert_frame_equal(newdf, res[0])


class TestReadHtmlLxml(tm.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestReadHtmlLxml, cls).setupClass()
        _skip_if_no('lxml')

    def read_html(self, *args, **kwargs):
        self.flavor = ['lxml']
        kwargs['flavor'] = kwargs.get('flavor', self.flavor)
        return read_html(*args, **kwargs)

    def test_data_fail(self):
        from lxml.etree import XMLSyntaxError
        spam_data = os.path.join(DATA_PATH, 'spam.html')
        banklist_data = os.path.join(DATA_PATH, 'banklist.html')

        with tm.assertRaises(XMLSyntaxError):
            self.read_html(spam_data, flavor=['lxml'])

        with tm.assertRaises(XMLSyntaxError):
            self.read_html(banklist_data, flavor=['lxml'])

    def test_works_on_valid_markup(self):
        filename = os.path.join(DATA_PATH, 'valid_markup.html')
        dfs = self.read_html(filename, index_col=0, flavor=['lxml'])
        tm.assert_isinstance(dfs, list)
        tm.assert_isinstance(dfs[0], DataFrame)

    @slow
    def test_fallback_success(self):
        _skip_if_none_of(('bs4', 'html5lib'))
        banklist_data = os.path.join(DATA_PATH, 'banklist.html')
        self.read_html(banklist_data, '.*Water.*', flavor=['lxml', 'html5lib'])

    def test_parse_dates_list(self):
        df = DataFrame({'date': date_range('1/1/2001', periods=10)})
        expected = df.to_html()
        res = self.read_html(expected, parse_dates=[0], index_col=0)
        tm.assert_frame_equal(df, res[0])

    def test_parse_dates_combine(self):
        raw_dates = Series(date_range('1/1/2001', periods=10))
        df = DataFrame({'date': raw_dates.map(lambda x: str(x.date())),
                        'time': raw_dates.map(lambda x: str(x.time()))})
        res = self.read_html(df.to_html(), parse_dates={'datetime': [1, 2]},
                             index_col=1)
        newdf = DataFrame({'datetime': raw_dates})
        tm.assert_frame_equal(newdf, res[0])


def test_invalid_flavor():
    url = 'google.com'
    nose.tools.assert_raises(ValueError, read_html, url, 'google',
                             flavor='not a* valid**++ flaver')


def get_elements_from_file(url, element='table'):
    _skip_if_none_of(('bs4', 'html5lib'))
    url = file_path_to_url(url)
    from bs4 import BeautifulSoup
    with urlopen(url) as f:
        soup = BeautifulSoup(f, features='html5lib')
    return soup.find_all(element)


@slow
def test_bs4_finds_tables():
    filepath = os.path.join(DATA_PATH, "spam.html")
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore')
        assert get_elements_from_file(filepath, 'table')


def get_lxml_elements(url, element):
    _skip_if_no('lxml')
    from lxml.html import parse
    doc = parse(url)
    return doc.xpath('.//{0}'.format(element))


@slow
def test_lxml_finds_tables():
    filepath = os.path.join(DATA_PATH, "spam.html")
    assert get_lxml_elements(filepath, 'table')


@slow
def test_lxml_finds_tbody():
    filepath = os.path.join(DATA_PATH, "spam.html")
    assert get_lxml_elements(filepath, 'tbody')


def test_same_ordering():
    _skip_if_none_of(['bs4', 'lxml', 'html5lib'])
    filename = os.path.join(DATA_PATH, 'valid_markup.html')
    dfs_lxml = read_html(filename, index_col=0, flavor=['lxml'])
    dfs_bs4 = read_html(filename, index_col=0, flavor=['bs4'])
    assert_framelist_equal(dfs_lxml, dfs_bs4)
