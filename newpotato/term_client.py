import argparse
import json
import logging

from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from newpotato.evaluate.eval_hitl import HITLEvaluator
from newpotato.evaluate.wire_functions import *
from newpotato.hitl_marina import HITLManager
from newpotato.modifications.oie_patterns import *
from newpotato.utils import get_triplets_from_user, print_tokens

console = Console()


class NPTerminalClient:
    def load_from_file(self):
        while True:
            console.print("[bold cyan]Enter path to HITL state file:[/bold cyan]")
            fn = input("> ")
            try:
                hitl = HITLManager.load(fn)
            except FileNotFoundError:
                console.print(f"[bold red]No such file or directory: {fn}[/bold red]")
            else:
                self.hitl = hitl
                console.print(
                    f"[bold cyan]Successfully loaded HITL state from {fn}[/bold cyan]"
                )
                return

    def write_patterns_to_file(self):
        while True:
            console.print("[bold cyan]Enter path to patterns .txt file:[/bold cyan]")
            fn = input("> ")
            try:
                self.hitl.extractor.save_patterns(fn)
            except FileNotFoundError:
                console.print(f"[bold red] No such file or directory: {fn}[/bold red]")
            else:
                console.print(
                    f"[bold cyan]Successfully saved extractor patterns to {fn}[/bold cyan]"
                )
                return

    def write_to_file(self):
        while True:
            console.print("[bold cyan]Enter path to HITL state file:[/bold cyan]")
            fn = input("> ")
            try:
                self.hitl.save(fn)
            except FileNotFoundError:
                console.print(f"[bold red] No such file or directory: {fn}[/bold red]")
            else:
                console.print(
                    f"[bold cyan]Successfully saved HITL state to {fn}[/bold cyan]"
                )
                return

    def clear_console(self):
        console.clear()

    def suggest_triplets(self):
        for sen in self.hitl.get_unannotated_sentences():
            for triplet in self.hitl.infer_triplets(sen):
                triplet_str = str(triplet)
                console.print("[bold yellow]How about this?[/bold yellow]")
                print_tokens(sen, self.hitl.extractor, console)
                console.print(f"[bold yellow]{triplet_str}[/bold yellow]")
                choice_str = None
                while choice_str not in ("c", "i", "s"):
                    choice_str = input("(c)orrect, (i)ncorrect, (s)top?")
                if choice_str == "s":
                    return
                positive = True if choice_str == "c" else False
                self.hitl.store_triplet(sen, triplet, positive=positive)

    # TODO: adapt this function (add input file instead of enter sentence)
    def classify(self):
        if not self.hitl.extractor.patterns:
            console.print("[bold red]No rules extracted yet[/bold red]")
            return
        else:
            console.print(
                "[bold green]Classifying a sentence, please provide one:[/bold green]"
            )
            text = input("> ")

            matches_by_text = self.hitl.extractor.extract_triplets_from_text(text)

            console.print("[bold green]Triplets:[/bold green]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Sentence")
            table.add_column("Triplets")
            table.add_column("Rules triggered")
            for sen, match_dict in matches_by_text.items():
                table.add_row(
                    sen,
                    ", ".join(str(t) for t in match_dict["triplets"]),
                    ", ".join(str(r) for r in match_dict["rules_triggered"]),
                )
            console.print(table)

    def print_status(self):
        status = self.hitl.get_status()

        status_lines = [f'{status["n_rules"]} rules', f'{status["n_sens"]} sentences']

        if status["n_sens"] > 0:
            status_lines.append(
                f'{status["n_annotated"]} of these annotated ({status["n_annotated"]/status["n_sens"]:.2%})'
            )

        console.print("\n".join(status_lines))

        triplets = self.hitl.get_true_triplets()
        self.print_triplets(triplets, max_n=10)

    def print_rules(self, top_n=20):
        if self.hitl.extractor.patterns is None:
            rules = self.hitl.get_rules(top_n)
        else:
            rules = self.hitl.extractor.patterns
        console.print("[bold green]Extracted Rules:[/bold green]")
        console.print(rules)

    def print_triplets(self, triplets_by_sen, max_n=None):
        console.print("[bold green]Current Triplets:[/bold green]")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Sentence")
        table.add_column("Triplets")

        for i, (sen, triplets) in enumerate(triplets_by_sen.items()):
            if max_n is not None and i > max_n:
                table.add_row("...", "...")
                break
            triplet_strs = [str(triplet) for triplet in triplets]
            table.add_row(sen, "\n".join(triplet_strs))

        console.print(table)

    # function to evaluate patterns on unseen data
    def evaluate(self, data=None):
        if self.hitl.extractor.patterns is None:
            console.print("[bold cyan]Enter path to patterns file:[/bold cyan]")
            fn = input("> ")
            try:
                self.hitl.extractor.load_patterns(fn)
            except FileNotFoundError:
                console.print(f"[bold red]No such file or directory: {fn}[/bold red]")
                console.print(
                    "[bold red]Run (R)ules to generate patterns from the current HITL state![/bold red]"
                )

        # gold data creation and prediction for LSOIE data
        if data:
            # data = "lsoie_wiki_dev.conll"
            self.hitl.extractor.temporary_triplets_creation(
                input=data, max_items=1000000
            )
        else:
            console.print("[bold cyan]Enter path to test data:[/bold cyan]")
            data = input("> ")

            try:
                self.hitl.extractor.temporary_triplets_creation(
                    input=data, max_items=1000000
                )
            except FileNotFoundError:
                console.print(f"[bold red]No such file or directory: {data}[/bold red]")
            else:
                return

        # evaluate triplets with WiRe57 scorer
        gold_data = data.split(".")[0] + "_gold.json"
        pred_data = data.split(".")[0] + "_pred.json"
        reference = json.load(open(gold_data))
        # gold_data = dict of documents, each doc a list of sents with a "tuples" attribute,
        # which is the list of reference tuples
        gold = {s["id"]: s["tuples"] for doc in reference.values() for s in doc}
        # TODO: remove ids from gold without prediction ?
        all_predictions = json.load(open(pred_data))
        predictions_by_OIE = split_tuples_by_extractor(gold.keys(), all_predictions)
        systems = predictions_by_OIE.keys()
        reports = {}

        for e in systems:
            report = ""
            logging.info(f"Evaluating {e} system ...")
            metrics, raw_match_scores = eval_system(gold, predictions_by_OIE[e])
            with open("raw_scores/" + e + "_prec_scores.dat", "w") as f:
                f.write(str(raw_match_scores[0]))
            with open("raw_scores/" + e + "_rec_scores.dat", "w") as f:
                f.write(str(raw_match_scores[1]))
            prec, rec = metrics["precision"], metrics["recall"]
            f1_score = f1(prec, rec)
            exactmatch_prec = (
                metrics["exactmatches_precision"][0]
                / metrics["exactmatches_precision"][1]
            )
            exactmatch_rec = (
                metrics["exactmatches_recall"][0] / metrics["exactmatches_recall"][1]
            )
            # weighted prec score, e.g. prec = 1, nr. of prediction tuples = 8 -> 12.5%
            # weighted rec score, e.g. rec = 0.6, nr. of reference tuples = 4 -> 15%
            report += "System {} prec/rec/f1: {:.1%} {:.1%} {:.3f}".format(
                e, prec, rec, f1_score
            )
            report += "\nSystem {} prec/rec of matches only (nr. of matches): {:.0%} {:.0%} ({})".format(
                e,
                metrics["precision_of_matches"],
                metrics["recall_of_matches"],
                # metrics["non-matches"],
                metrics[
                    "matches"
                ],  # this seems to be incorrect -> 'non-matches' required?
            )
            report += "\n{} were exactly correct, out of {} predicted / the reference {}.".format(
                metrics["exactmatches_precision"][0],
                metrics["exactmatches_precision"][1],
                metrics["exactmatches_recall"][1],
            )
            report += "\nExact-match prec/rec/f1: {:.1%} {:.1%} {:.3f}".format(
                exactmatch_prec, exactmatch_rec, f1(exactmatch_prec, exactmatch_rec)
            )
            reports[f1_score] = report
        sorted_reports = [a[1] for a in sorted(reports.items(), reverse=True)]
        print("\n" + "\n\n".join(sorted_reports))

        # evaluator = HITLEvaluator(self.hitl)
        # results = evaluator.get_results()
        # for key, value in results.items():
        #     console.print(f"{key}: {value}")
        # if fn:
        #     evaluator.write_events_to_file(fn)

    def print_graphs(self):
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Sentence")
        table.add_column("Graph")
        for sen, graph in self.hitl.extractor.parsed_graphs.items():
            # table.add_row(sen, str(graph["main_edge"]))
            table.add_row(sen, str(graph))
        console.print(table)

    def _upload_file(self, fn):
        if fn.endswith("txt"):
            self.upload_txt(fn)
        else:
            console.print("[bold red]Unknown file format, must be txt[/bold red]")

    def upload_file(self):
        console.print("[bold cyan]Enter path of txt or jsonl file:[/bold cyan]")
        fn = input("> ")
        self._upload_file(fn)

    def upload_txt(self, fn):
        console.print("[bold cyan]Parsing text...[/bold cyan]")
        with open(fn) as f:
            for line in tqdm(f):
                self.hitl.extractor.get_graphs(line.strip())
        console.print("[bold cyan]Done![/bold cyan]")

    def annotate(self):
        while True:
            console.print(
                "Type the start of the sentence you would like to annotate or enter R to get random unannotated sentences. Or press ENTER to return to finish annotating and return to main menu"
            )
            raw_query = input("> ")
            query = raw_query.strip().lower()
            if not query:
                break
            if query == "r":
                for sen in self.hitl.get_unannotated_sentences(
                    random_order=True, max_sens=3
                ):
                    get_triplets_from_user(sen, self.hitl, console)
            else:
                cands = [
                    sen
                    for sen in self.hitl.extractor.parsed_graphs
                    if sen.lower().startswith(query)
                ]
                if len(cands) > 20:
                    console.print("more than 20 matches, please refine")
                    continue
                for i, sen in enumerate(cands):
                    console.print(f"{i}\t{sen}")

                console.print("Enter ID of the sentence you want to annotate")
                choice = input("> ")
                try:
                    sen = cands[int(choice)]
                except (ValueError, IndexError):
                    console.print("[bold red]invalid choice[/bold red]")
                else:
                    get_triplets_from_user(sen, self.hitl, console)

    def run_oie(self):
        # get status data
        status = self.hitl.get_status()
        total_cnt = status["n_annotated"]

        # # unsupervised rule learning
        # top_n = 50
        # pc = self.hitl.generalise_graph(top_n, method="unsupervised")
        # print(pc)
        # top_patterns = pc.most_common(top_n)

        # # get simplified patterns
        # simple_patterns, total_cnt = simplify_patterns(top_patterns, strict=False)
        # print(simple_patterns)
        # print("Total count: ", total_cnt)

        # open saved oie patterns file
        # f = open("p_train.txt", "r")
        # patterns = f.read()

        # # supervised rule learning
        # top_n = 20
        # pc = self.hitl.generalise_graph(method="supervised", check_vars=True)
        # patterns = [key for key, _ in pc.most_common(top_n)]
        # print(patterns)

        # pattern_cnt = sum(pc.values())
        # print(f"{pattern_cnt=}")
        # print(
        #     f"{pattern_cnt/total_cnt:.2%} of annotated sentences have a pattern"
        # )  # not exactly because of multiple patterns per sentence

    def _run(self):
        while True:
            self.print_status()
            console.print(
                "[bold cyan]Choose an action:\n\t(U)pload\n\t(G)raphs\n\t(A)nnotate\n\t(R)ules\n\t(S)uggest\n\t(I)nference\n\t(E)valuate\n\t(L)oad\n\t(W)rite\n\t(P)atterns\n\t(C)lear\n\t(Q)uit\n\t(H)elp\n\t(O)pen Information Extraction[/bold cyan]"
            )
            choice = input("> ").upper()
            if choice in ("S", "I") and not self.hitl.extractor.is_trained:
                console.print(
                    "[bold red]That choice requires the extractor to be trained, run (R)ules first![/bold red]"
                )
            elif choice == "U":
                self.upload_file()
            elif choice == "G":
                self.print_graphs()
            elif choice == "A":
                self.annotate()
            elif choice == "R":
                self.print_rules()
            elif choice == "S":
                self.suggest_triplets()
            elif choice == "I":
                self.classify()
            elif choice == "E":
                self.evaluate()
            elif choice == "L":
                self.load_from_file()
            elif choice == "W":
                self.write_to_file()
            elif choice == "P":
                self.write_patterns_to_file()
            elif choice == "C":
                self.clear_console()
            elif choice == "Q":
                console.print("[bold red]Exiting...[/bold red]")
                break
            # TODO: remove this and update help info
            elif choice == "O":
                self.run_oie()
            elif choice == "H":
                console.print(
                    "[bold cyan]Help:[/bold cyan]\n"
                    + "\t(U)pload: Upload a file with input text\n"
                    + "\t(G)raphs: Print graphs of parsed sentences\n"
                    + "\t(A)nnotate: Annotate the latest sentence\n"
                    + "\t(R)ules: Extract rules from the annotated graphs\n"
                    + "\t(S)uggest: Suggest inferred triplets for sentences\n"
                    + "\t(I)nference: Use rules to predict triplets from sentences\n"
                    + "\t(E)valuate: Evaluate rules on annotated sentences\n"
                    + "\t(L)oad: Load HITL state from file\n"
                    + "\t(W)rite: Write HITL state to file\n"
                    + "\t(P)atterns: Write extractor patterns to file\n"
                    + "\t(C)lear: Clear the console\n"
                    + "\t(Q)uit: Exit the program\n"
                    + "\t(H)elp: Show this help message\n"
                    + "\t(O)pen Information Extraction: Transform hyperedges into abstract patterns\n"
                )

            else:
                console.print("[bold red]Invalid choice[/bold red]")

    def run_interactive(self):
        try:
            self._run()
        except KeyboardInterrupt:
            pass

        while True:
            console.print("[bold red]Save HITL state? (y/n)[/bold red]")
            s = input().strip().lower()
            if s == "y":
                self.write_to_file()
                break
            elif s == "n":
                break

    def run(self, args):
        if args.load_state is None:
            console.print("[cyan]no state file provided, initializing new HITL[/cyan]")
            self.hitl = HITLManager(args.extractor_type)
        else:
            console.print(f"[cyan]loading HITL state from {args.load_state}[/cyan]")
            self.hitl = HITLManager.load(args.load_state, args.oracle)

        if args.load_patterns:
            console.print(
                f"[cyan]loading extractor patterns from {args.load_patterns}[/cyan]"
            )
            self.hitl.extractor.load_patterns(args.load_patterns)

        if args.upload_text:
            console.print(f"[cyan]loading text from {args.upload_text}[/cyan]")
            self._upload_file(args.upload_text)

        if args.get_rules:
            console.print("[bold cyan]getting rules[/bold cyan]")
            if args.rules_cnt:
                self.print_rules(args.rules_cnt)
            else:
                self.print_rules()

        if args.evaluate:
            self.evaluate(args.evaluate)

        if args.save_patterns:
            self.hitl.extractor.save_patterns(args.save_patterns)
            console.print(
                f"[bold cyan]Successfully saved extractor patterns to {args.save_patterns}[/bold cyan]"
            )

        if args.save_state:
            self.hitl.save(args.save_state)
            console.print(
                f"[bold cyan]Saved HITL state to {args.save_state}[/bold cyan]"
            )

        if args.interactive:
            self.run_interactive()


def get_args():
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-o", "--oracle", action="store_true")
    parser.add_argument("-i", "--interactive", action="store_true")
    parser.add_argument("-r", "--get_rules", action="store_true")
    parser.add_argument("-rc", "--rules_cnt", default=20, type=int)
    parser.add_argument("-e", "--evaluate", default=None, type=str)
    parser.add_argument("-l", "--load_state", default=None, type=str)
    parser.add_argument("-lp", "--load_patterns", default=None, type=str)
    parser.add_argument("-u", "--upload_text", default=None, type=str)
    parser.add_argument("-p", "--save_patterns", default=None, type=str)
    parser.add_argument("-s", "--save_state", default=None, type=str)
    parser.add_argument("-x", "--extractor_type", default="ud", type=str)
    return parser.parse_args()


def main():
    args = get_args()
    logging.basicConfig(
        format="%(asctime)s : %(module)s (%(lineno)s) - %(levelname)s - %(message)s",
        force=True,
    )
    logging.getLogger().setLevel(logging.WARNING)
    if args.interactive or args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    client = NPTerminalClient()
    client.run(args)


if __name__ == "__main__":
    main()
