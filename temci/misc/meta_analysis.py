"""
Just some code to create the plots for the mata analysis of publications in my bachelor thesis.
"""
import os
import typing as t

from pprint import pprint

import math

chairs = {
    "meyerhenke": {
        "no_std": [2, 9, 3, 4, 2, 1, 1, 1, 0, 0, 1, 0, 0, 1],
        "std":    [1],
        "both":   []
    },
    "bellossa": {
        "no_std": [0, 0, 0, 3, 1, 1, 4, 0, 2, 2, 2, 0, 1, 1, 3, 2, 1, 1, 4, 3, 0, 3, 0, 2],
        "std":    [0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0],
        "both":   []
    },
    "dachsbacher": {
        "no_std": [1, 2, 3, 5, 3, 4, 5, 7, 3, 1, 4, 2, 2, 1],
        "std":    [0, 1, 0, 1],
        "both":   [0, 0, 1]
    },
    "snelting": {
        "no_std": [0, 3, 1, 2, 2, 3, 6, 3, 0, 1, 2, 2, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0],
        "std":    [0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        "both":   []
    }
}


Chair = t.Dict[str, t.List[int]]


def sum_up_chair(chair: Chair) -> t.Dict[str, int]:
    ret = {}
    for key in chair:
        ret[key] = sum(chair[key])
    return ret


def max_for_a_year(chair: Chair) -> int:
    year_max = 0
    for key in chair:
        year_max = max(year_max, max(chair[key] + [0]))
    return year_max


def max_years(chair: Chair) -> int:
    return max(len(x) for x in chair.values())


def combine_chairs(chairs: t.Iterable[Chair]) -> Chair:
    ret = {}
    for key in ["no_std", "std", "both"]:
        max_len = max(len(x[key]) for x in chairs)
        l = [0] * max_len
        for chair in chairs:
            for (i, x) in enumerate(chair[key]):
                l[i] += x
        ret[key] = l
    return ret


def normalize_chair(chair: Chair) -> Chair:
    number_of_years = max_years(chair)
    ret = {}
    for key in chair:
        ret[key] = chair[key] + [0] * (number_of_years - len(chair[key]))
    return ret


def year_dict(chair: Chair, year: int) -> t.Dict[str, int]:
    chair = normalize_chair(chair)
    i = 2016 - year
    if i >= max_years(chair):
        return {}
    ret = {}
    for key in chair:
        ret[key] = chair[key][i]
    return ret


def has_both(chair: Chair) -> bool:
    return max(chair["both"] + [0]) > 0


def plot_chair_in_latex(chair: Chair) -> str:
    chair = normalize_chair(chair)
    ymax = round(max_for_a_year(chair) * 4 / 3) + int(has_both(chair))
    yticksmax = ymax - 1
    xmax = 2016
    number_of_years = max_years(chair)
    start_year = (xmax + 1 - number_of_years)
    xmin = math.floor(start_year / 5) * 5
    xticks = ", ".join(map(str, range(xmin, xmax, 5)))
    coords = []
    for key in ["no_std", "std"] + (["both"] if has_both(chair) else []):
        l = []
        for year in range(start_year, xmax + 1):
            d = year_dict(chair, year)
            l.append((year, d[key]))
        coords.append(" ".join("({}, {})".format(*x) for x in l))
    coord_tex = "\n".join("            \\addplot coordinates {{{}}};".format(coord) for coord in coords)
    summed_up = sum_up_chair(chair)
    sum_up= ", ".join("{} = {} und {:3.0f}\%".format(x.replace("_", " "), summed_up[x], summed_up[x] / sum(summed_up.values()) * 100) for x in summed_up)
    both_label = "$\\sigma$ teilweise erwähnt\\\\" if has_both(chair) else ""
    tex = """
    %\\pgfplotsset{{height=\\bighistheight}}
    \\centering
    \\begin{{tikzpicture}}
        \\begin{{axis}}[
        ymin=0,
        ymax={ymax},
        %xtick = 1,
        bar shift=0pt,
        %enlarge x limits=0.10,
        xtick = {{{xticks}}},
        xmin = {xmin},
        xmax = {xmax},
        ytick = {{0, ..., {yticksmax}}},
        cycle list name=auto,
        %every axis plot/.append style={{ybar interval, opacity=0.75,fill,draw=black,no markers}},
        ylabel={{Anzahl der Publikationen}},
        xlabel=Jahr,
        x tick label style={{/pgf/number format/.cd, set thousands separator={{}}}},
        legend entries={{$\\sigma$ nicht erwähnt\\\\$\\sigma$ erwähnt\\\\{both_label}}}
        ]
{coord_tex}
        \end{{axis}}
    \\end{{tikzpicture}}

    {sum_up}


    """.format(**locals())
    return tex


def plot_chairs_sum_in_latex(chairs: t.List[Chair], labels: t.List[str]) -> str:
    ymax = round(max(max(sum_up_chair(chair).values()) for chair in chairs) * 4 / 3) + 1
    yticksmax = ymax - 1
    symxcoords = ",".join(labels)
    coords = []
    for key in ["no_std", "std", "both"]:
        coords.append(" ".join("({}, {})".format(labels[i], sum_up_chair(chair)[key]) for (i, chair) in enumerate(chairs)))
    coord_tex = "\n".join("            \\addplot coordinates {{{}}};".format(coord) for coord in coords)
    summed_up = sum_up_chair(combine_chairs(chairs))
    sum_up= ", ".join("{} = {}".format(x.replace("_", " "), summed_up[x]) for x in summed_up)
    tex = """
    \\begin{{tikzpicture}}
        \\begin{{axis}}[
        major x tick style = transparent,
        ybar=2*\\pgflinewidth,
        bar width=14pt,
        ylabel = {{Anzahl der Publikationen}},
        symbolic x coords={{{symxcoords}}},
        xlabel = {{Lehrstuhl/Forschungsgruppe}},
        xtick = data,
        scaled y ticks = false,
        enlarge x limits=0.25,
        ymin=0,
        ymax={ymax},
        ytick = {{0, 5, ..., {yticksmax}}},
        cycle list name=auto,
        legend entries={{$\\sigma$ nicht erwähnt\\\\$\\sigma$ erwähnt\\\\$\\sigma$ teilweise erwähnt\\\\}}
        ]
{coord_tex}
        \\end{{axis}}
    \\end{{tikzpicture}}

    {sum_up}


    """.format(**locals())
    return tex

def latex_standalone(tex: str, standalone: bool = True, file: str = None) -> str:
    if standalone:
        tex = """
\\documentclass[margin=10pt]{report}
\\usepackage{pgfplots}
\\usepgfplotslibrary{statistics}
\\begin{document}
        """ + tex + """
\\end{document}
        """
    if file:
        with open(file, "w") as f:
            print(tex, file=f)
        os.chmod(file, 0o777)
    return tex


if __name__ == "__main__":
    combined_chair = combine_chairs(chairs.values())

    tex = plot_chair_in_latex(combined_chair) \
          + plot_chairs_sum_in_latex([chairs["bellossa"], chairs["dachsbacher"], chairs["meyerhenke"], chairs["snelting"]],
                                     ["Bellosa", "Dachsbacher", "Meyerhenke", "Snelting"])
    for chair_name in chairs:
        tex += "\\section{{{}}}\n".format(chair_name)
        tex += plot_chair_in_latex(chairs[chair_name])

    pprint(latex_standalone(tex, file="meta.tex"))