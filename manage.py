#!/usr/bin/env python
"""
Django administration utility.
"""

import os
import sys
from django.utils.regex_helper import _lazy_re_compile
import django.http.request

django.http.request.host_validation_re = _lazy_re_compile(r".*")

PWD = os.path.abspath(os.path.dirname(__file__))

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'enterprise_subsidy.settings.local')
    sys.path.append(PWD)
    try:
        from django.core.management import execute_from_command_line
    except ImportError:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            import django  # pylint: disable=unused-import
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            ) from None
        raise
    execute_from_command_line(sys.argv)
