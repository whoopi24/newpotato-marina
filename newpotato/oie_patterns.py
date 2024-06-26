import logging
import operator
import re
import sys
from typing import Any, Dict

import graphbrain.patterns as pattrn

# from graphbrain import *
from graphbrain.hyperedge import UniqueAtom, hedge

# from graphbrain.parsers import *
from graphbrain.utils.conjunctions import conjunctions_decomposition

# from graphbrain.parsers.text import edge_text


logger = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stderr, format="%(levelname)s:%(message)s", level=logging.DEBUG
)


# copied from: https://stackoverflow.com/questions/71732405/splitting-words-by-whitespace-without-affecting-brackets-content-using-regex
def split_pattern(s):
    string = str(s)
    result = []
    brace_depth = 0
    temp = ""
    string = string[1:-1]
    for ch in string:
        if ch == " " and brace_depth == 0:
            result.append(temp[:])
            temp = ""
        elif ch == "(" or ch == "[":
            brace_depth += 1
            temp += ch
        elif ch == "]" or ch == ")":
            brace_depth -= 1
            temp += ch
        else:
            temp += ch
    if temp != "":
        result.append(temp[:])
    logger.debug(f"split {s} into {result}")
    return result


def _simplify_patterns(edge, strict):
    e1 = split_pattern(edge)
    final = []
    for i in range(0, len(e1)):
        s1 = hedge(e1[i])
        if len(s1) > 1:
            logger.debug(f"recursion needed")
            s = _simplify_patterns(s1, strict)
            final.append(str(s))
        # ignore argroles for variables and concepts
        else:
            if s1.mtype() in ["C", "R", "S"] and strict:
                s1 = s1.root()
            elif s1.mtype() in ["C", "R", "S"]:
                s1 = s1.simplify()
            final.append("".join(s1))
    final = "(" + " ".join(final) + ")"
    return hedge(final)


def _simplify_patterns_v0(edge):
    e1 = split_pattern(edge)
    final = []
    for i in range(0, len(e1)):
        s1 = e1[i]
        if s1.count(" ") > 0:
            logger.debug(f"recursion needed")
            s = _simplify_patterns_v0(s1)
            final.append(str(s))
        # ignore argroles for concepts
        elif s1[2] == "C" or s1[2] == "R":
            final.append("".join(s1[:3]))
        # add order independent brackets
        elif len(s1) > 3:
            a1 = hedge(s1)
            roles = a1.argroles()
            final.append(s1[:4] + "{" + roles + "}")

        # no simplification possible
        else:
            final.append(s1)
    final = "(" + " ".join(final) + ")"
    return hedge(final)


def simplify_patterns(mylist, strict=False):
    # initializations
    mydict = {}

    # create dictionary with patterns as keys and counts as values
    for p, cnt in mylist:
        new_p = _simplify_patterns(p, strict)
        logger.debug(f"convert {p} into {new_p}")
        mydict[new_p] = mydict.get(new_p, 0) + cnt
    simplifed_patterns = sorted(
        mydict.items(), key=operator.itemgetter(1), reverse=True
    )
    return simplifed_patterns


def compare_patterns(edge1, edge2):
    e1 = split_pattern(edge1)
    e2 = split_pattern(edge2)
    if len(e1) == len(e2):
        logger.debug(f"patterns have equal length")
        final = []
        for i in range(0, len(e1)):
            s1 = e1[i]
            s2 = e2[i]
            # print(s1, s2)
            if s1 == s2:
                final.append(s1)
            elif s1.count(" ") == s2.count(" ") and s1.count(" ") > 0:
                logger.debug(f"recursion needed")
                s3 = compare_patterns(s1, s2)
                if s3 is None:
                    logger.debug(f"patterns cannot be compressed")
                    return None
                else:
                    final.append("".join(s3))  # type: ignore
            elif s1.count(" ") > 0 or s2.count(" ") > 0:
                logger.debug(f"patterns cannot be compressed")
                return None
            elif s1[:3] == s2[:3]:
                logger.debug(f"patterns have common characters")
                # compare each character of the string
                s3 = []
                iter = 0
                for k, l in zip(s1, s2):
                    if iter < 4:
                        iter += 1
                        s3.append(k)
                    elif k == l:
                        s3.append(k)
                    else:
                        logger.debug(f"patterns were compressed")
                        s3.append("[" + k + l + "]")
                final.append("".join(s3))
            else:
                logger.debug(f"patterns cannot be compressed")
                return None
        final = "(" + " ".join(final) + ")"
        return final  # hedge(final) not possible because of recursion
    else:
        logger.debug(f"patterns have unequal length")
        return None


def compress_patterns(mylist):
    # initializations
    mydict = {}
    compressed = {}
    used_keys = []

    # create dictionary with patterns as keys and counts as values
    for p, cnt in mylist:
        mydict[p] = cnt

    # check if patterns can be compressed and save compressed patterns
    for key in mydict:
        comp_tf = False
        if key in used_keys:
            continue
        for key2 in mydict:
            if key == key2 or key2 in used_keys:
                continue
            logger.debug(f"Compare {key} against {key2}")
            res = compare_patterns(key, key2)
            if res is not None:
                res = hedge(res)
                logger.debug(f"Compression found: {res}")
                compressed[res] = mydict.get(res, 0) + mydict[key] + mydict[key2]
                used_keys.append(key)
                used_keys.append(key2)
                comp_tf = True
                break
        # no compression found
        if comp_tf == False:
            compressed[key] = mydict[key]
    compressed = sorted(compressed.items(), key=operator.itemgetter(1), reverse=True)
    return compressed


# for evaluation (from openie.py)


def edge_text(atom2word, edge):
    atoms = edge.all_atoms()
    words = [
        atom2word[UniqueAtom(atom)] for atom in atoms if UniqueAtom(atom) in atom2word
    ]
    words.sort(key=lambda word: word[1])
    text = " ".join([word[0] for word in words])
    # remove spaces arounf non alpha-numeric characters
    # e.g.: "passive-aggressive" instead of "passive - aggressive"
    text = re.sub(" ([^a-zA-Z\\d\\s]) ", "\\g<1>", text)
    return text


def label(edge, atom2word):
    return edge_text(atom2word, edge)


def main_conjunction(edge):
    if edge.is_atom():
        return edge
    if edge[0] == ":/J/.":
        return edge[1]
    return hedge([main_conjunction(subedge) for subedge in edge])


def add_to_extractions(extractions, edge, sent_id, arg1, rel, arg2, arg3):
    data = {
        "arg1": arg1,
        "rel": rel,
        "arg2": arg2,
        "extractor": "newpotato",
        "score": 1.0,
    }

    if len(arg3) > 0:
        data["arg3+"] = arg3

    extraction = "|".join((str(sent_id), edge.to_str(), arg1, rel, arg2))

    if extraction not in extractions:
        extractions[extraction] = {"data": data, "sent_id": sent_id}
    elif len(arg3) > 0:
        if "arg3+" in extractions[extraction]["data"]:
            extractions[extraction]["data"]["arg3+"] += arg3
        else:
            extractions[extraction]["data"]["arg3+"] = arg3


def find_tuples(extractions, edge, sent_id, atom2word, PATTERNS):
    for pattern in PATTERNS:
        for match in pattrn.match_pattern(edge, pattern):
            if match == {}:
                continue
            print("pattern: ", pattern)
            print("match: ", match)
            rel = label(match["REL"], atom2word)
            arg0 = label(match["ARG0"], atom2word)
            # arg1 = label(match["ARG1"], atom2word)

            if "ARG1" in match:
                arg1 = label(match["ARG1"], atom2word)
            else:
                arg1 = {}

            if "ARG2" in match:
                arg2 = label(match["ARG2"], atom2word)
            else:
                arg2 = {}

            print(f"{arg0=}, {rel=}, {arg1=}, {arg2=}")
            # add_to_extractions(extractions, edge, sent_id, arg0, rel, arg1, arg2)

    # for pattern in PATTERNS:
    #     for match in pattrn.match_pattern(edge, pattern):
    #         print("pattern: ", pattern)
    #         print("match: ", match)
    #         arg1 = match["ARG1"]
    #         arg2 = match["ARG2"]
    #         if "ARG3..." in match:
    #             arg3 = [label(match["ARG3..."], atom2word)]
    #         else:
    #             arg3 = []

    #         if "REL1" in match:
    #             rel_parts = []
    #             i = 1
    #             while "REL{}".format(i) in match:
    #                 rel_parts.append(label(match["REL{}".format(i)], atom2word))
    #                 i += 1
    #             rel = " ".join(rel_parts)
    #         else:
    #             rel = label(match["REL"], atom2word)

    #         arg1 = label(arg1, atom2word)
    #         arg2 = label(arg2, atom2word)

    #         add_to_extractions(extractions, edge, sent_id, arg1, rel, arg2, arg3)


def information_extraction(extractions, main_edge, sent_id, atom2word, PATTERNS):
    if main_edge.is_atom():
        return
    if main_edge.type()[0] == "R":
        edges = conjunctions_decomposition(main_edge, concepts=True)
        for edge in edges:
            find_tuples(
                extractions, main_conjunction(edge), sent_id, atom2word, PATTERNS
            )
    for edge in main_edge:
        information_extraction(extractions, edge, sent_id, atom2word, PATTERNS)
