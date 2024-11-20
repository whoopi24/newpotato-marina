import json
import logging
import os
import pickle
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional  # , Tuple

import stanza
from graphbrain import hgraph
from graphbrain.hyperedge import Atom, Hyperedge
from graphbrain.learner.classifier import from_json as classifier_from_json
from graphbrain.learner.rule import Rule
from graphbrain.parsers import create_parser
from graphbrain.utils.conjunctions import conjunctions_decomposition, predicate
from tuw_nlp.text.utils import gen_tsv_sens, tuple_if_list

from newpotato.datatypes import Triplet
from newpotato.extractors.extractor import Extractor

# from newpotato.modifications.classifier import Classifier
from newpotato.modifications.oie_patterns import *
from newpotato.modifications.pattern_ops import *
from newpotato.modifications.patterns import PatternCounter


@dataclass
class HITLManager:
    """A class to manage the HITL process and store parsed graphs.

    Attributes:
        parsed_graphs (Dict[str, Dict[str, Any]]): A dict mapping
            sentences to parsed graphs.
        annotated_graphs (Dict[str, List[Hyperedge]]): A dict mapping
            sentences to annotated graphs.
        triplets (Dict[str, List[Tuple]]): A dict mapping sentences to
            triplets.
        latest (Optional[str]): The latest sentence.
        extractor (Extractor): The extractor that uses classifiers to extract triplets from graphs.
    """

    def __init__(self, extractor_type):
        self.latest = None
        self.text_to_triplets = defaultdict(list)
        self.oracle = None
        self.extractor_type = extractor_type
        self.init_extractor()
        logging.info("HITL manager initialized")

    def init_extractor(self):
        if self.extractor_type == "ud":
            from newpotato.extractors.graph_extractor import GraphBasedExtractor

            self.extractor = GraphBasedExtractor()
        elif self.extractor_type == "graphbrain":
            from newpotato.extractors.graphbrain_extractor_PC import GraphbrainExtractor

            self.extractor = GraphbrainExtractor()
        else:
            raise ValueError(f"unsupported extractor type: {self.extractor_type}")

    def load_extractor(self, extractor_data):
        self.extractor = Extractor.from_json(extractor_data)

    def load_triplets(self, triplet_data, oracle=False):
        text_to_triplets = {
            tuple_if_list(item["text"]): [
                (
                    Triplet.from_json(triplet[0]),
                    triplet[1],
                )
                for triplet in item["triplets"]
            ]
            for item in triplet_data
        }

        if oracle:
            self.oracle = text_to_triplets
            self.text_to_triplets = defaultdict(list)
        else:
            self.text_to_triplets = defaultdict(list, text_to_triplets)

    @staticmethod
    def load(fn, oracle=False):
        logging.info(f"loading HITL state from {fn=}")
        with open(fn) as f:
            data = json.load(f)
        return HITLManager.from_json(data, oracle=oracle)

    @staticmethod
    def from_json(data: Dict[str, Any], oracle=False):
        """
        load HITLManager from saved state

        Args:
            data (dict): the saved state, as returned by the to_json function

        Returns:
            HITLManager: a new HITLManager object with the restored state
        """
        hitl = HITLManager(extractor_type=data["extractor_type"])
        hitl.load_triplets(data["triplets"], oracle=oracle)
        hitl.load_extractor(data["extractor_data"])
        return hitl

    def to_json(self) -> Dict[str, Any]:
        """
        get the state of the HITLManager so that it can be saved

        Returns:
            dict: a dict with all the HITLManager object's attributes that are relevant to
                its state
        """

        return {
            "triplets": [
                {
                    "text": text,
                    "triplets": [
                        (triplet[0].to_json(), triplet[1])
                        for triplet in triplets
                        if triplet[0] != False
                    ],
                }
                for text, triplets in self.text_to_triplets.items()
            ],
            "extractor_data": self.extractor.to_json(),
            "extractor_type": self.extractor_type,
        }

    def save(self, fn: str):
        """
        save HITLManager state to a file

        Args:
            fn (str): path of the file to be written (will be overwritten if it exists)
        """
        with open(fn, "w") as f:
            f.write(json.dumps(self.to_json()))

    def get_status(self) -> Dict[str, Any]:
        """
        return basic stats about the HITL state
        """

        return {
            "n_sens": len(self.extractor.parsed_graphs),
            "n_annotated": len(self.text_to_triplets),
            "n_rules": self.extractor.get_n_rules(),
        }

    def get_rules(self, *args, **kwargs):
        return self.extractor.get_rules(self.text_to_triplets, *args, **kwargs)

    def print_rules(self, console):
        return self.extractor.print_rules(console)

    def infer_triplets(self, sen: str, **kwargs) -> List[Triplet]:
        return self.extractor.infer_triplets(sen, **kwargs)

    def get_true_triplets(self) -> Dict[str, List[Triplet]]:
        """
        Get the triplets, return everything except the latest triplets.

        Returns:
            Dict[str, List[Triplet]]: The triplets.
        """

        return {
            sen: [triplet for triplet, positive in triplets if positive is True]
            for sen, triplets in self.text_to_triplets.items()
            if sen != "latest"
        }

    def delete_triplet(self, text: str, triplet: Triplet):
        """
        Delete the triplet.

        Args:
            text (str): the text to delete the triplet for.
            triplet (Triplet): the triplet to delete
        """

        if text == "latest":
            assert (
                self.latest is not None
            ), "no parsed graphs stored, can't use `latest`"
            return self.delete_triplet(self.latest, triplet)
        # assert self.is_parsed(text), f"unparsed text: {text}"
        logging.info(f"deleting from triplets: {text=}, {triplet=}")
        logging.info(self.text_to_triplets[text])
        self.text_to_triplets[text].remove((triplet, True))

    def store_triplet(
        self,
        text: str,
        triplet: Triplet,
        positive=True,
    ):
        """
        Store the triplet.

        Args:
            text (str): the text to store the triplet for.
            triplet (Triplet): the triplet to store
            positive (bool): whether to store the triplet as a positive (default) or negative
                example
        """

        if text == "latest":
            assert (
                self.latest is not None
            ), "no parsed graphs stored, can't use `latest`"
            return self.store_triplet(self.latest, triplet, positive)
        logging.info(f"appending to triplets: {text=}, {triplet=}")
        self.text_to_triplets[text].append((triplet, positive))

    def get_unannotated_sentences(
        self, max_sens: Optional[int] = None, random_order: bool = False
    ) -> Generator[str, None, None]:
        """
        get a list of sentences that have been added and parsed but not yet annotated

        Args:
            max_sens (int): the maximum number of sentences to return. If None (this is the
                default) or larger than the total number of unannotated sentences, all
                unannotated sentences are returned
            random_order (bool): if False (default), sentences are yielded in the order of
                the self.parsed_graphs dict, which is always the same. If True, a random
                sample is generated, with a new random seed on each function call.

        Returns:
            Generator[str] the unannotated sentences
        """
        sens = [
            sen
            for sen in self.extractor.parsed_graphs
            if sen != "latest" and sen not in self.text_to_triplets
        ]
        n_graphs = len(sens)
        max_n = min(max_sens, n_graphs) if max_sens is not None else n_graphs

        if random_order:
            random.seed()
            logging.debug(f"sampling {max_n} indices from {n_graphs}")
            indices = set(random.sample(range(n_graphs), max_n))
            logging.debug(f"sample indices: {indices}")
            yield from (
                sen for i, sen in enumerate(sens) if i in indices and sen != "latest"
            )
        else:
            yield from sens[:max_n]

    # my own functions
    def parse_sent_with_ann_eval(
        self,
        PATTERNS,
        extractions,
        max_items,
        expect_mappable=True,
        input="lsoie_wiki_dev.conll",
    ):
        stream = open(input, "r", encoding="utf-8")
        iter = 0
        parser = create_parser(lang="en", corefs=False)
        last_sent = ""
        for sen_idx, sen in enumerate(gen_tsv_sens(stream)):
            if iter == max_items:
                break
            print(f"processing sentence {sen_idx}")
            # get sentence
            sent = []
            for _, tok in enumerate(sen):
                sent.append(tok[1])

            # parse sentence
            sent = " ".join(sent)
            if sent == last_sent:
                continue
            last_sent = sent
            print(sent)
            parse_result = parser.parse(sent)
            for parse in parse_result["parses"]:
                main_edge = parse["main_edge"]
                atom2word = parse["atom2word"]
                if main_edge:
                    # print(f"{sent=}, {main_edge=}, {atom2word=}")
                    information_extraction(
                        extractions, main_edge, sen_idx, atom2word, PATTERNS
                    )

            # next round
            iter += 1

        # return(extractions)

    # def generalise_graph_v2(self, hg, top_n=50):

    #     # transform hyperedges into abstract patterns
    #     pc = PatternCounter(
    #         expansions={
    #             "(* * *)",
    #             "(* * * *)",
    #         },
    #         match_roots={"+/B"},
    #         count_subedges=False,
    #     )

    #     for e in hg.all():
    #         if hg.is_primary(e):
    #             try:
    #                 pc.count(e)
    #             except:
    #                 continue

    #     return pc.patterns.most_common(top_n)

    def generalise_graph(self, top_n=50, path="hg_test.db"):

        # transform hyperedges into abstract patterns
        pc = PatternCounter(
            expansions={
                "(* * *)",
                "(* * * *)",
            },
            # match_roots={"+/B"},
            count_subedges=False,
        )

        # 1st version
        # for _, graph in self.extractor.parsed_graphs.items():
        #     edge = graph["main_edge"]
        #     # exclusion of conjunctions
        #     edges = conjunctions_decomposition(edge, concepts=True)
        #     for e in edges:
        #         try:
        #             pc.count(e)
        #         except:
        #             continue

        # 2nd version (https://graphbrain.net/tutorials/hypergraph-operations.html#parse-sentence-and-add-hyperedge-to-hypergraph)
        # takes longer than 1st version
        # if os.path.exists(path):
        #     os.remove(path)
        # hg = hgraph(path)
        # for _, graph in self.extractor.parsed_graphs.items():
        #     edge = graph["main_edge"]
        #     # exclusion of conjunctions
        #     edges = conjunctions_decomposition(edge, concepts=True)
        #     for e in edges:
        #         hg.add(e)

        # for e in hg.all():
        #     if hg.is_primary(e):  # works and removes duplicated patterns
        #         pc.count(e)

        # 3rd version: use existing hg object
        hg = hgraph(path)
        for edge in hg.all():
            if hg.is_primary(edge):
                pc.count(edge)

        return pc.patterns.most_common(top_n)
