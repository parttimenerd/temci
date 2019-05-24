""" Initialize temci for use as a library """

# see https://github.com/leanprover/lean4/commit/1c1d8933e

from temci.utils import util
util.allow_all_imports = True
import temci.scripts.cli  # side effects may include: registering settings, loading settings object, ...
from temci.utils import number, settings

number.FNumber.init_settings(settings.Settings()["report/number"])