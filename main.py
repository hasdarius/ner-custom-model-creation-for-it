import os
import pdfplumber
import spacy

import train_custom_ner
from os.path import isfile, join
from os import path, listdir

CONCEPTS_SCORES = {
    "intern": {
        "Seniority": 0,
        "Max Programming Language": 2,
        "Max Tool/Framework": 4,
        "Max Certification": 2,
        "Max Programming Concept": 8,
        "Max IT Specialization": 0,
        "Full Programming Language": 7,
        "Partial Programming Language": 3,
        "Full Tool/Framework": 3,
        "Partial Tool/Framework": 1.5,
        "Full Certification": 0,
        "Partial Certification": 0,
        "Full Programming Concept": 5,
        "Partial Programming Concept": 3,
        "Full IT Specialization": 0,
        "Partial IT Specialization": 0
    },
    "junior": {
        "Seniority": 1,
        "Max Programming Language": 4,
        "Max Tool/Framework": 8,
        "Max Certification": 3,
        "Max Programming Concept": 10,
        "Max IT Specialization": 2,
        "Full Programming Language": 7,
        "Partial Programming Language": 3,
        "Full Tool/Framework": 5,
        "Partial Tool/Framework": 2,
        "Full Certification": 1,
        "Partial Certification": 0.5,
        "Full Programming Concept": 3,
        "Partial Programming Concept": 1.5,
        "Full IT Specialization": 1,
        "Partial IT Specialization": 0.5
    },
    "mid": {
        "Seniority": 2,
        "Max Programming Language": 6,
        "Max Tool/Framework": 12,
        "Max Certification": 4,
        "Max Programming Concept": 12,
        "Max IT Specialization": 3,
        "Full Programming Language": 5,
        "Partial Programming Language": 2,
        "Full Tool/Framework": 7,
        "Partial Tool/Framework": 3,
        "Full Certification": 3,
        "Partial Certification": 1.5,
        "Full Programming Concept": 2,
        "Partial Programming Concept": 1,
        "Full IT Specialization": 3,
        "Partial IT Specialization": 1.5
    },
    "senior": {
        "Seniority": 3,
        "Max Programming Language": 8,
        "Max Tool/Framework": 15,
        "Max Certification": 4,
        "Max Programming Concept": 15,
        "Max IT Specialization": 4,
        "Full Programming Language": 5,
        "Partial Programming Language": 2,
        "Full Tool/Framework": 7,
        "Partial Tool/Framework": 3,
        "Full Certification": 4,
        "Partial Certification": 2,
        "Full Programming Concept": 2,
        "Partial Programming Concept": 1,
        "Full IT Specialization": 3,
        "Partial IT Specialization": 1.5
    }
}


def get_max_seniority(list_of_seniorities):
    # print(list_of_seniorities)
    seniority_priority_list = ['senior', 'mid', 'junior', 'intern']
    final_seniority_priority_list = ['senior', 'mid', 'junior', 'intern']
    for priority in seniority_priority_list:
        if priority not in list_of_seniorities:
            final_seniority_priority_list.remove(priority)
    return final_seniority_priority_list[0]


def get_cv_ranking_score(cv_file_dictionary, job_description_dictionary):
    max_required_seniority = get_max_seniority(list(map(lambda x: x.lower(), job_description_dictionary['Seniority'])))
    max_given_seniority = get_max_seniority(list(map(lambda x: x.lower(), cv_file_dictionary['Seniority'])))
    score = CONCEPTS_SCORES[max_given_seniority]['Seniority']
    print("Max required seniority: " + max_required_seniority)
    print("Max given seniority: " + max_given_seniority)
    max_absolute_seniority = get_max_seniority([max_required_seniority, max_given_seniority])
    print("Max absolute seniority: " + max_absolute_seniority)
    for label in job_description_dictionary:
        if label != 'Seniority':
            required_label_values_list = job_description_dictionary[label]
            given_label_values_list = cv_file_dictionary[label]
            max_values = max(2 * len(required_label_values_list),
                             CONCEPTS_SCORES[max_absolute_seniority]['Max ' + label])
            overflow = len(given_label_values_list) - max_values
            if overflow > 0:
                score -= overflow * CONCEPTS_SCORES[max_required_seniority]['Full ' + label]
            for given_label_value in given_label_values_list:
                if given_label_value in required_label_values_list:
                    score += CONCEPTS_SCORES[max_required_seniority]['Full ' + label]
                    print("Full: " + given_label_value)
                else:
                    score += CONCEPTS_SCORES[max_required_seniority]['Partial ' + label]
                    print("Partial: " + given_label_value)
    return score


def generate_dictionary_of_concepts(doc):
    final_dictionary = {}
    for ent in doc.ents:
        final_dictionary[ent.label_].append(ent.text)
    return final_dictionary


def read_cv_entities_from_pdf(document_path, nlp):
    pdf = pdfplumber.open(document_path)
    text = ""
    for page in pdf.pages:
        text = text + "\n" + page.extract_text()
    doc = nlp(text)
    return generate_dictionary_of_concepts(doc)


def read_cv_entities_from_txt(document_path, nlp):
    text_file = open(document_path, "r")
    text = text_file.read()
    doc = nlp(text)
    return generate_dictionary_of_concepts(doc)


def rank_cvs(job_description_text, cv_folder, model):
    nlp = spacy.load(model)
    doc = nlp(job_description_text)
    job_description_entities = generate_dictionary_of_concepts(doc)  # read dictionary entities
    cv_files = [file for file in listdir(cv_folder) if isfile(join(cv_folder, file))]
    score_list = []
    for cv_file in cv_files:
        _, file_extension = os.path.splitext(cv_file)
        match file_extension:
            case ".pdf":
                cv_entities_dictionary = read_cv_entities_from_pdf(cv_file, nlp)
            case ".txt":
                cv_entities_dictionary = read_cv_entities_from_txt(cv_file, nlp)
            case _:
                cv_entities_dictionary = {}  # here would be better to throw exception, decide with David
        cv_score = get_cv_ranking_score(cv_entities_dictionary, job_description_entities)
        score_list.append((cv_file, cv_score))
    return score_list.sort(key=lambda cv: cv[1])


if __name__ == "__main__":
    # main("Data/it_dataset.csv")
    job_description_dictionary = {'Seniority': ["Junior"], 'Programming Language': ["Python", "Scala"],
                                  'Certification': ["oracle oca certification"],
                                  'Tool/Framework': ["Spark", "Django", "Flusk", "BigQuery"],
                                  'IT Specialization': ["Data Engineer"],
                                  'Programming Concept': ["Big Data", "Artificial intelligence", "Scrum"]}
    cv_file_dictionary = {'Seniority': ["mid", "Junior"], 'Programming Language': ["Python", "Java", "C"],
                          'Certification': [],
                          'Tool/Framework': ["Spark", "Django", "Spring", "SqlServer", "GitHub"],
                          'IT Specialization': ["Data Engineer"],
                          'Programming Concept': ["OOP", "Scrum", "Rest"]}
    print(get_cv_ranking_score(cv_file_dictionary, job_description_dictionary))


def main(input_file):
    if not path.exists(train_custom_ner.CUSTOM_SPACY_MODEL):
        json_file_name = train_custom_ner.csv_to_json_with_labels(input_file, '-')
        training_data = train_custom_ner.json_to_spacy_format(json_file_name)
        train_custom_ner.fine_tune_and_save_custom_model(training_data,
                                                         new_model_name='technology_it_model',
                                                         output_dir=train_custom_ner.CUSTOM_SPACY_MODEL)
    # here we will test the model
