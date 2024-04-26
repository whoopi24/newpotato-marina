import logging
import operator
from typing import Any, Dict

from graphbrain import hedge

logger = logging.getLogger(__name__)
logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)


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


def _simplify_patterns(edge):
    e1 = split_pattern(edge)
    final = []
    for i in range(0, len(e1)):
        s1 = e1[i]
        if s1.count(" ") > 0:
            logger.debug(f"recursion needed")
            s = _simplify_patterns(s1)
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


def simplify_patterns(mylist):
    # initializations
    mydict = {}

    # create dictionary with patterns as keys and counts as values
    for p, cnt in mylist:
        new_p = _simplify_patterns(p)
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
                final.append("".join(s3))  # type: ignore
            elif s1.count(" ") > 0 or s2.count(" ") > 0:
                logger.debug(f"patterns cannot be compressed")
                return None
            elif s1[:3] == s2[:3]:
                logger.debug(f"patterns have common characters")
                # compare each character of the string

                # ToDo
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
