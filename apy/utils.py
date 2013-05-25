import datetime

import pytz


def ms_to_datetime(value):
    return pytz.utc.localize(datetime.datetime.utcfromtimestamp(value / 1000))


def datetime_to_ms(value):
    return round(float(value.astimezone(pytz.utc).strftime('%s.%f')) * 1000)
