from .rundata import RunDataStatsHelper, RunData
from ..utils.typecheck import *
from ..utils.registry import AbstractRegistry, register
import click, yaml, numpy
from ..utils.settings import Settings

class ReporterRegistry(AbstractRegistry):

    settings_key_path = "report"
    use_key = "reporter"
    use_list = False
    default = "console"


class AbstractReporter:

    def __init__(self, misc_settings: dict = None, stats_helper: RunDataStatsHelper = None):
        if stats_helper is None:
            runs = []
            typecheck(Settings()["report/in"], ValidYamlFileName())
            with open(Settings()["report/in"], "r") as f:
                runs = yaml.load(f)
            self.stats_helper = RunDataStatsHelper.init_from_dicts(Settings()["stats"], runs)
        else:
            self.stats_helper = stats_helper

    def report(self):
        raise NotImplementedError()

@register(ReporterRegistry, "console", Dict())
class ConsoleReporter(AbstractReporter):

    def report(self):
        with click.open_file(Settings()["report/out"], mode='w') as f:
            for block in self.stats_helper.runs:
                assert isinstance(block, RunData)
                print("{descr:<20} ({num:>5} single benchmarkings)"
                      .format(descr=block.description(), num=len(block.data[block.properties[0]])), file=f)
                for prop in sorted(block.properties):
                    mean = numpy.mean(block[prop])
                    stdev = numpy.std(block[prop])
                    print("\t {prop:<12} mean = {mean:>15.5f}, "
                          "deviation = {dev_perc:>10.5%} ({dev:>15.5f})".format(
                        prop=prop, mean=mean,
                        dev=stdev, dev_perc=stdev/mean
                    ))

            self._report_list("Equal program blocks",
                              self.stats_helper.get_evaluation(with_equal=True,
                                                               with_uncertain=False,
                                                               with_unequal=False), f)
            self._report_list("Unequal program blocks",
                              self.stats_helper.get_evaluation(with_equal=False,
                                                               with_uncertain=False,
                                                               with_unequal=True), f)
            self._report_list("Uncertain program blocks",
                              self.stats_helper.get_evaluation(with_equal=True,
                                                               with_uncertain=True,
                                                               with_unequal=True), f)

    def _report_list(self, title: str, list, file):
        if len(list) != 0:
            print(title, file=file)
            print("####################", file=file)
        for item in list:
            print("\t {} ⟷ {}".format(item["data"][0].description(),
                                       item["data"][1].description()), file=file)
            for prop in sorted(item["properties"]):
                prop_data = item["properties"][prop]
                perc = prop_data["p_val"]
                if prop_data["unequal"]:
                    perc = 1 - perc
                print("\t\t {descr:<12} probability = {perc:>10.5%}, speed up = {speed_up:>10.5%}"
                      .format(descr=prop_data["description"], perc=perc,
                              speed_up=prop_data["speed_up"]), file=file)