import logging
from typing import Union, Optional, Dict

import pandas as pd
from pandas.tseries.offsets import YearBegin, YearEnd
import pytz
import requests
from bs4 import BeautifulSoup

from entsoe.exceptions import InvalidPSRTypeError, InvalidBusinessParameterError
from .exceptions import NoMatchingDataError, PaginationError
from .mappings import Area, NEIGHBOURS, lookup_area
from .parsers import parse_prices, parse_netpositions

'''
from .mappings import Area, NEIGHBOURS, lookup_area
from .parsers import parse_prices, parse_loads, parse_generation, \
    parse_installed_capacity_per_plant, parse_crossborder_flows, \
    parse_unavailabilities, parse_contracted_reserve, parse_imbalance_prices_zip, \
    parse_imbalance_volumes_zip, parse_netpositions, parse_procured_balancing_capacity, \
    parse_water_hydro
from .decorators import retry, paginated, year_limited, day_limited, documents_limited
'''

__title__ = "get_entsoe"
__version__ = "0.5.4"
__author__ = "EnergieID.be, Frank Boerman"
__license__ = "MIT"

URL = 'https://transparency.entsoe.eu/api'


class EntsoeRawClient:
    # noinspection LongLine
    """
        Client to perform API calls and return the raw responses API-documentation:
        https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html#_request_methods
        Attributions: Parts of the code for parsing Entsoe responses were copied
        from https://github.com/tmrowco/electricitymap
        """

    def __init__(
            self, api_key: str, session: Optional[requests.Session] = None,
            retry_count: int = 1, retry_delay: int = 0,
            proxies: Optional[Dict] = None, timeout: Optional[int] = None):
        """
        Parameters
        ----------
        api_key : str
        session : requests.Session
        retry_count : int
            number of times to retry the call if the connection fails
        retry_delay: int
            amount of seconds to wait between retries
        proxies : dict
            requests proxies
        timeout : int
        """
        if api_key is None:
            raise TypeError("API key cannot be None")
        self.api_key = api_key
        if session is None:
            session = requests.Session()
        self.session = session
        self.proxies = proxies
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.timeout = timeout

    #@retry
    def _base_request(self, params: Dict, start: pd.Timestamp,
                      end: pd.Timestamp) -> requests.Response:
        """
        Parameters
        ----------
        params : dict
        start : pd.Timestamp
        end : pd.Timestamp
        Returns
        -------
        requests.Response
        """
        start_str = self._datetime_to_str(start)
        end_str = self._datetime_to_str(end)

        base_params = {
            'securityToken': self.api_key,
            'periodStart': start_str,
            'periodEnd': end_str
        }
        params.update(base_params)

        logging.debug(f'Performing request to {URL} with params {params}')
        response = self.session.get(url=URL, params=params,
                                    proxies=self.proxies, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.find_all('text')
            if len(text):
                error_text = soup.find('text').text
                if 'No matching data found' in error_text:
                    raise NoMatchingDataError
                elif "check you request against dependency tables" in error_text:
                    raise InvalidBusinessParameterError
                elif "is not valid for this area" in error_text:
                    raise InvalidPSRTypeError
                elif 'amount of requested data exceeds allowed limit' in error_text:
                    requested = error_text.split(' ')[-2]
                    allowed = error_text.split(' ')[-5]
                    raise PaginationError(
                        f"The API is limited to {allowed} elements per "
                        f"request. This query requested for {requested} "
                        f"documents and cannot be fulfilled as is.")
                elif 'requested data to be gathered via the offset parameter exceeds the allowed limit' in error_text:
                    requested = error_text.split(' ')[-9]
                    allowed = error_text.split(' ')[-30][:-2]
                    raise PaginationError(
                        f"The API is limited to {allowed} elements per "
                        f"request. This query requested for {requested} "
                        f"documents and cannot be fulfilled as is.")
            raise e
        else:
            # ENTSO-E has changed their server to also respond with 200 if there is no data but all parameters are valid
            # this means we need to check the contents for this error even when status code 200 is returned
            # to prevent parsing the full response do a text matching instead of full parsing
            # also only do this when response type content is text and not for example a zip file
            if response.headers.get('content-type', '') == 'application/xml':
                if 'No matching data found' in response.text:
                    raise NoMatchingDataError
            return response

    @staticmethod
    def _datetime_to_str(dtm: pd.Timestamp) -> str:
        """
        Convert a datetime object to a string in UTC
        of the form YYYYMMDDhh00
        Parameters
        ----------
        dtm : pd.Timestamp
            Recommended to use a timezone-aware object!
            If timezone-naive, UTC is assumed
        Returns
        -------
        str
        """
        if dtm.tzinfo is not None and dtm.tzinfo != pytz.UTC:
            dtm = dtm.tz_convert("UTC")
        fmt = '%Y%m%d%H00'
        ret_str = dtm.strftime(fmt)
        return ret_str

    def query_day_ahead_prices(self, country_code: Union[Area, str],
                               start: pd.Timestamp, end: pd.Timestamp) -> str:
        """
        Parameters
        ----------
        country_code : Area|str
        start : pd.Timestamp
        end : pd.Timestamp
        Returns
        -------
        str
        """
        area = lookup_area(country_code)
        params = {
            'documentType': 'A44',
            'in_Domain': area.code,
            'out_Domain': area.code
        }
        response = self._base_request(params=params, start=start, end=end)
        return response.text

    def query_net_position(self, country_code: Union[Area, str],
                           start: pd.Timestamp, end: pd.Timestamp, dayahead: bool = True) -> str:
        """
        Parameters
        ----------
        country_code : Area|str
        start : pd.Timestamp
        end : pd.Timestamp
        dayahead : bool
        Returns
        -------
        str
        """
        area = lookup_area(country_code)
        params = {
            'documentType': 'A25',  # Allocation result document
            'businessType': 'B09',  # net position
            'Contract_MarketAgreement.Type': 'A01',  # daily
            'in_Domain': area.code,
            'out_Domain': area.code
        }
        if not dayahead:
            params.update({'Contract_MarketAgreement.Type': "A07"})

        response = self._base_request(params=params, start=start, end=end)
        return response.text



class EntsoePandasClient(EntsoeRawClient):
    #@year_limited
    def query_net_position(self, country_code: Union[Area, str],
                           start: pd.Timestamp, end: pd.Timestamp, dayahead: bool = True) -> pd.Series:
        """
        Parameters
        ----------
        country_code
        start
        end
        Returns
        -------
        """
        area = lookup_area(country_code)
        text = super(EntsoePandasClient, self).query_net_position(
            country_code=area, start=start, end=end, dayahead=dayahead)
        series = parse_netpositions(text)
        series = series.tz_convert(area.tz)
        series = series.truncate(before=start, after=end)
        return series

    #@year_limited
    def query_day_ahead_prices(
            self, country_code: Union[Area, str], start: pd.Timestamp,
            end: pd.Timestamp) -> pd.Series:
        """
        Parameters
        ----------
        country_code : Area|str
        start : pd.Timestamp
        end : pd.Timestamp
        Returns
        -------
        pd.Series
        """
        area = lookup_area(country_code)
        text = super(EntsoePandasClient, self).query_day_ahead_prices(
            country_code=area, start=start, end=end)
        series = parse_prices(text)
        series = series.tz_convert(area.tz)
        series = series.truncate(before=start, after=end)
        return series

