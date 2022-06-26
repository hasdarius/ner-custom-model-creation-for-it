import os
import re
from os import listdir
from os.path import isfile, join
from pprint import pprint

import pdfplumber
import spacy
from business_rules import run_all
from business_rules.actions import BaseActions, rule_action
from business_rules.fields import FIELD_NUMERIC
from business_rules.variables import BaseVariables, numeric_rule_variable

import train_custom_ner
from constants import CONCEPTS_SCORES, REASONING_PERFECT_MATCH, REASONING_PERFECT_MATCH_TYPE, \
    REASONING_GRAPH_CONNECTION_P1, REASONING_GRAPH_CONNECTION_P2, LABELS_LIST, REASONING_PENALIZATION, \
    REASONING_GRAPH_CONNECTION_P3
from knowledge_graph import get_shortest_path_between_concepts, generate_knowledge_graph_components_from_files


class RequiredLabelInfo:
    def __init__(self, label_name, required_values, max_required_seniority, max_absolute_seniority,
                 max_required_values=9999):
        self.name = label_name
        self.values = required_values
        self.max_absolute_seniority = max_absolute_seniority
        self.loss_value = 0.25
        self.max_required_values = max_required_values
        self.actual_loss_values = 0


class RequiredLabelInfoVariables(BaseVariables):

    def __init__(self, label_info):
        self.label_info = label_info

    @numeric_rule_variable(label='Maximum number of words with a specific label before being penalized')
    def get_max_required_value_for_label(self):
        label_info = self.label_info
        label_info.max_required_values = max(2 * len(label_info.values),
                                             CONCEPTS_SCORES[label_info.max_absolute_seniority][
                                                 'Max ' + label_info.name])
        return label_info.max_required_values


class RequiredLabelInfoActions(BaseActions):

    def __init__(self, label_info):
        self.label_info = label_info

    @rule_action(params={"given_values_length": FIELD_NUMERIC})
    def penalize(self, given_values_length):
        self.label_info.actual_loss_values = (
                                                     self.label_info.max_required_values - given_values_length) * self.label_info.loss_value


def apply_business_rules(max_absolute_seniority, max_required_seniority, label_name, required_label_values,
                         given_label_values, feedback_list):
    given_label_values_length = len(given_label_values)
    rules = [
        # expiration_days < 5 AND current_inventory > 20
        {"conditions":
             {"name": "get_max_required_value_for_label",
              "operator": "less_than",
              "value": given_label_values_length,
              },
         "actions": [
             {"name": "penalize",
              "params": {"given_values_length": given_label_values_length},
              }
         ]}]
    required_label_info = RequiredLabelInfo(label_name, required_label_values, max_required_seniority,
                                            max_absolute_seniority)
    if run_all(rule_list=rules,
               defined_variables=RequiredLabelInfoVariables(required_label_info),
               defined_actions=RequiredLabelInfoActions(required_label_info),
               stop_on_first_trigger=True
               ):
        feedback_list.append(REASONING_PENALIZATION + "<<" + label_name + ">>.")
    return required_label_info.actual_loss_values


def get_max_seniority(list_of_seniorities):
    seniority_priority_list = ['senior', 'mid', 'junior', 'intern']
    final_seniority_priority_list = ['senior', 'mid', 'junior', 'intern']
    for priority in seniority_priority_list:
        if priority not in list_of_seniorities:
            final_seniority_priority_list.remove(priority)
    if final_seniority_priority_list:
        return final_seniority_priority_list[0]
    return seniority_priority_list[1]  # None


def get_cv_ranking_score(cv_entities_dictionary, job_description_entities_dictionary, feedback_list, graph):
    max_required_seniority = get_max_seniority(
        list(map(lambda x: x.lower(), job_description_entities_dictionary['Seniority'])))
    max_given_seniority = get_max_seniority(list(map(lambda x: x.lower(), cv_entities_dictionary['Seniority'])))
    score = 0
    if max_given_seniority is not None:
        score = CONCEPTS_SCORES[max_given_seniority]['Seniority']
    max_absolute_seniority = get_max_seniority([max_required_seniority, max_given_seniority])
    required_relevant_keys = ['Programming Language', 'Programming Concept', 'Tool/Framework']
    knowledge_graph_required_labels = [x for key in required_relevant_keys for x in
                                       job_description_entities_dictionary.get(key)]
    maximum_score_for_job_description = get_max_score_for_job_description(job_description_entities_dictionary,
                                                                          max_absolute_seniority)
    print(maximum_score_for_job_description)
    for label in job_description_entities_dictionary:
        if label != 'Seniority':
            required_label_values_list = job_description_entities_dictionary[label]
            given_label_values_list = cv_entities_dictionary[label]

            score += apply_business_rules(max_absolute_seniority, max_required_seniority, label,
                                          required_label_values_list,
                                          given_label_values_list, feedback_list)
            for given_label_value in given_label_values_list:
                if given_label_value in required_label_values_list:
                    score += CONCEPTS_SCORES[max_required_seniority]['Full ' + label]
                    feedback_list.append(
                        REASONING_PERFECT_MATCH + "<<" + given_label_value + ">>" + REASONING_PERFECT_MATCH_TYPE + label + ".")
                else:
                    score += score_partial_matches(feedback_list, given_label_value, graph,
                                                   knowledge_graph_required_labels, label, max_required_seniority)

    print(score)
    return min(1, (score / maximum_score_for_job_description))


def score_partial_matches(feedback_list, given_label_value, graph, knowledge_graph_required_labels, label,
                          max_required_seniority):
    for required_label_value in knowledge_graph_required_labels:
        shortest_path, nr_of_shortest_paths = get_shortest_path_between_concepts(
            given_label_value.lower(),
            required_label_value.lower(), graph)
        if shortest_path:
            reasoning = REASONING_GRAPH_CONNECTION_P1 + "<<" + required_label_value + ">>, <<" + given_label_value + ">>" + REASONING_GRAPH_CONNECTION_P2 + str(
                nr_of_shortest_paths) + REASONING_GRAPH_CONNECTION_P3
            for connection_tuple in shortest_path:
                reasoning = reasoning + "<<" + connection_tuple[0][0] + ">> which <<" + connection_tuple[1][
                    'relationship'] + ">> with <<" + connection_tuple[0][1] + ">>, "

            feedback_list.append(reasoning)
            return CONCEPTS_SCORES[max_required_seniority]['Partial ' + label]
    return 0


def generate_dictionary_of_concepts(doc):
    final_dictionary = {}
    for ent in doc.ents:
        final_dictionary.setdefault(ent.label_, set()).add(ent.text.lower().strip())
    detected_keys = final_dictionary.keys()
    for label in LABELS_LIST:
        if label not in detected_keys:
            final_dictionary[label] = set()
    print('This is the dictionary of concepts:')
    pprint(final_dictionary)
    print('-----------------------------------------------------')

    return final_dictionary


def read_cv_entities_from_pdf(document_path, nlp):
    pdf = pdfplumber.open(document_path)
    text = ""
    for page in pdf.pages:
        text = text + "\n" + page.extract_text()
    text = re.sub(r"[^a-zA-Z0-9]", " ", text)
    doc = nlp(text)
    return generate_dictionary_of_concepts(doc)


def read_cv_entities_from_txt(document_path, nlp):
    text_file = open(document_path, "r")
    text = text_file.read()
    text = re.sub(r"[^a-zA-Z0-9]", " ", text)
    doc = nlp(text)
    return generate_dictionary_of_concepts(doc)


def get_max_score_for_job_description(job_description_entities, seniority):
    score = 0
    scores_for_seniority = CONCEPTS_SCORES[seniority]
    for label in job_description_entities:
        if label != 'Seniority':
            nr_of_instances = len(job_description_entities[label])
            nr_of_partial_instances = scores_for_seniority['Max ' + label] - nr_of_instances
            score += nr_of_instances * scores_for_seniority['Full ' + label] + nr_of_partial_instances * scores_for_seniority['Partial ' + label]
    return score


def rank_cvs(job_description_text, cv_folder):
    graph = generate_knowledge_graph_components_from_files('Data/edges.csv')
    custom_nlp = spacy.load(train_custom_ner.CUSTOM_SPACY_MODEL)
    job_description_text = re.sub(r"[^a-zA-Z0-9]", " ", job_description_text)
    nlp_doc = custom_nlp(job_description_text)
    job_description_entities = generate_dictionary_of_concepts(nlp_doc)  # read job description entities in dictionary
    cv_files = [file for file in listdir(cv_folder) if isfile(join(cv_folder, file))]
    score_list = []
    for cv_file in cv_files:
        _, file_extension = os.path.splitext(cv_file)
        feedback_list = []
        if file_extension == ".pdf":
            cv_entities_dictionary = read_cv_entities_from_pdf(cv_folder + '/' + cv_file, custom_nlp)
        else:
            if file_extension == ".txt":
                cv_entities_dictionary = read_cv_entities_from_txt(cv_folder + '/' + cv_file, custom_nlp)
            else:
                cv_entities_dictionary = {}
        cv_score = get_cv_ranking_score(cv_entities_dictionary, job_description_entities, feedback_list, graph)
        score_list.append((cv_file, cv_score, feedback_list))
    return sorted(score_list, key=lambda cv: cv[1], reverse=True)