#!/usr/bin/env python3

import json
import smtplib
import argparse
import re
import os
import random
import copy
from fractions import Fraction

from email import encoders
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase

help_string = """
python3 assign_fair.py data.json keys.json command

  create_keys
  write_invitation_files
  send_invitation_emails
  calc_assignment
"""


def gen_a_key():
    key = random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
    return "PASSWORD" + key

def personalize(person, string):
    for key, value in person.items():
        string = re.sub("{" + key + "}", value, string)
    return string

def read_json_file(filename):
    with open(filename) as f:
        return json.loads(f.read())

class Collector():

    def __init__(self, data_file, key_file, really_send_emails=False):
        self.really_send_emails = really_send_emails;
        data = read_json_file(data_file)
        # the ordering of the people and topic elements is important b/c later only indecces are used
        self.people = data['people']
        self.topics =  data['topics']
        assert len(self.people) == len(self.topics)
        assert len(self.topics) == len(set([t['title'] for t in self.topics]))
        # we correlate the index for a topic to the string it produces (we need just that to retrive the preferences)
        self.topics_by_str = {self.format_topic(t): index for index, t in enumerate(self.topics)}
        self.options =  data['options']
        self.key_file = key_file

    def format_topic(self, topic):
        txt = '"{0}" am {1} von {2}'.format(topic['title'], topic['date'], topic['tutor'])
        if '{' in txt or '}' in txt:
            raise Exception("Nothing related to the topic may contain '{' or '}'")
        return '{' + txt + '}'

    def create_keys(self):
        if os.path.isfile(self.key_file):
            raise Exception("Want to create key file but it allready exists.")
        keys = set()
        while len(keys) < len(self.people):
            keys.add(gen_a_key())
        keys = list(keys)

        keys = [{'email': person_email, 'key': key} for person_email, key in zip(self.people.keys(), keys)]
        with open(self.key_file, 'w') as f:
            f.write(json.dumps(keys, indent=2))

    def get_invitation_attachment(self, key_entry):
        person = self.people[key_entry['email']]
        topics = list(self.topics_by_str.keys())
        random.shuffle(topics)
        txt = "\n".join(topics)
        filename = "{0}.{1}.({2}).txt".format(person['first_name'], person['last_name'], key_entry['key']);
        return (txt, filename)

    def write_invitation_files(self):
        if not os.path.isfile(self.key_file):
            raise Exception("cannot find key file")
        keys = read_json_file(self.key_file)
        os.makedirs(self.options['preference_directory'], exist_ok=True)
        for k in keys:
            (txt, filename) = self.get_invitation_attachment(k)
            with open(os.path.join(self.options['preference_directory'], filename), 'w') as f:
                f.write(txt)

    def send_invitation_emails(self):
        if not os.path.isfile(self.key_file):
            raise Exception("cannot find key file")
        keys = read_json_file(self.key_file)
        msgs = []
        for k in keys:
            p = self.people[k['email']]
            msg = MIMEMultipart()
            msg['Subject'] = personalize(p, self.options['subject'])
            msg['From'] = self.options['from']
            msg['To'] = k['email'] if self.really_send_emails else self.options['test_reciver']
            msg.attach(MIMEText(personalize(p, "\n".join(self.options['body']))))

            txt, filename = self.get_invitation_attachment(k)
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(txt)
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(attachment)

            msgs.append(msg)

        smtp = smtplib.SMTP(self.options['smtp_host'])
        smtp.starttls()
        smtp.login(self.options['smtp_username'], self.options['smtp_password'])
        for m in msgs:
            smtp.send_message(m)
        smtp.quit()


    topic_split_regex = re.compile('(?<=})\s*(?={)')
    def extract_preferences(self, filename):
        with open(filename, 'r') as f:
            txt = f.read().strip()
        topics = self.topic_split_regex.split(txt)
        preference_list = []
        for t in topics:
            if t not in self.topics_by_str:
                raise Exception("invalid topic in {filename}: {topic}".format(filename=filename, topic=t))
            preference_list.append(self.topics_by_str[t])
        return preference_list

    def retrive_preferences(self):
        if not os.path.isfile(self.key_file):
            raise Exception("cannot find key file")
        keys = read_json_file(self.key_file)
        prefs = {}
        for filename in [f for f in os.listdir(self.options['preference_directory'])
                           if f.endswith('.txt')]:
            matching_keys = [k for k in keys if '(' + k['key'] + ')' in filename]
            if len(matching_keys) < 1:
                raise Exception("file {} doesn't contain any known key".format(filename))
            if len(matching_keys) > 1:
                raise Exception("file {} doesn't contain more than one known key".format(filename))
            k = matching_keys[0]
            prefs[k['email']] = self.extract_preferences(os.path.join(self.options['preference_directory'], filename))
        return prefs

    def calc_assignment(self):
        prefs_dict = self.retrive_preferences()
        # sort the preferences correctly, now we just use the index to identify to person
        index_person_map = {}
        prefs_list = []
        index_with_pref = 0
        index_without_pref = len(prefs_dict)
        for person_email in self.people.keys():
            if person_email in prefs_dict:
                prefs_list.append(prefs_dict[person_email])
                index_person_map[index_with_pref] = person_email
                index_with_pref += 1
            else:
                index_person_map[index_without_pref] = person_email
                index_without_pref += 1
        random_assignment = probablisitic_serial_assignmnet(prefs_list)
        random_assignment = fill_incomplete_random_assignment(random_assignment)
        print('\n'.join([' '.join(map(str,a)) for a in random_assignment]))
        assert is_valid_random_assignment(random_assignment)
        deterministic_assignment = fix_random_assignmnet(random_assignment)
        deterministic_assignment_dict = {
                index_person_map[person_idx]: assigned_topic_idx
                for person_idx, assigned_topic_idx in enumerate(deterministic_assignment)}
        return self.deterministic_assignment_as_string(deterministic_assignment_dict)

    def deterministic_assignment_as_string(self, deterministic_assignment):
        def format_line(person_email, topic_idx):
            person = self.people[person_email]
            topic = self.topics[topic_idx]
            return self.options['result_line_format'].format(
                    first_name = person['first_name'],
                    last_name = person['last_name'],
                    email = person_email,
                    title = topic['title'],
                    date = topic[ 'date'],
                    tutor = topic['tutor']
                )
        return '\n'.join(format_line(person_email, topic_idx) for person_email, topic_idx in deterministic_assignment.items())



def is_valid_random_assignment(random_assignment):
    if len(random_assignment) == 0: return False
    n = len(random_assignment)
    sum1 = [Fraction(0) for _ in range(n)]
    sum2 = [Fraction(0) for _ in range(n)]
    for i, inner in enumerate(random_assignment):
        if len(inner) != n: return False
        for j, value in enumerate(inner):
            if type(value) is not Fraction: return False
            sum1[i] += value
            sum2[j] += value
    if any((s != 1 for s in sum1)): return False
    if any((s != 1 for s in sum2)): return False
    return True

def fill_incomplete_random_assignment(incomplete_ra):
    random_assignment = copy.deepcopy(incomplete_ra)
    num_people = len(incomplete_ra)
    num_topics = len(incomplete_ra[0])
    if num_people == num_topics:
        return random_assignment
    assert num_people < num_topics
    new_people = num_topics - num_people
    topic_probabilities = [0 for _ in range(num_topics)]
    for inner in random_assignment:
        for topic_idx, value in enumerate(inner):
            topic_probabilities[topic_idx] += value
    new_topics = [(1 - p)/new_people for p in topic_probabilities]
    for _ in range(new_people):
        random_assignment.append([copy.deepcopy(new_topics)])
    return random_assignment

def probablisitic_serial_assignmnet(prefs):
    num_people = len(prefs)
    num_topics = len(prefs[0])
    assert num_topics >= num_people
    assert all([len(p) == num_topics for p in prefs])
    # how much of each topic es eaten allredy
    topic_eaten = [Fraction(0) for _ in range(num_topics)]
    # everyone eats at speed one, so we need to eat until time is one
    elapsed_time = Fraction(0)
    # which preference is currently eaten per person
    eating_pref = [0 for _ in range(num_people)]
    eaten_per_person_per_topic = [[Fraction(0) for _ in range(num_topics)] for _ in range(num_people)]

    while elapsed_time < 1:
        number_of_eaters = [0 for _ in range(num_topics)]
        for person_idx, p in enumerate(prefs):
            number_of_eaters[p[eating_pref[person_idx]]] += 1
        topic_eaten_time = [
                    (1 - topic_eaten[topic_idx]) / number_of_eaters[topic_idx]
                if number_of_eaters[topic_idx] != 0 else
                    2
            for topic_idx in range(num_topics)
        ]
        delta_time = min(min(topic_eaten_time), 1 - elapsed_time)

        for person_idx, p in enumerate(prefs):
            topic_idx = p[eating_pref[person_idx]]
            eaten_per_person_per_topic[person_idx][topic_idx] += delta_time
            topic_eaten[topic_idx] += delta_time
        for person_idx, p in enumerate(prefs):
            topic_idx = p[eating_pref[person_idx]]
            if topic_eaten[topic_idx] == 1:
                eating_pref[person_idx] += 1
        elapsed_time += delta_time
    return eaten_per_person_per_topic




def fix_random_assignmnet(random_assignment):
    random_assignment = copy.deepcopy(random_assignment)
    n = len(random_assignment)
    def find_start():
        for i, inner in enumerate(random_assignment):
            for j, value in enumerate(inner):
                if value != 0 and value != 1:
                    return (i, j)
        return None
    def find_cycle(start):
        cycle = [start]
        while True:
            # vertical next

            ## check if we can finish
            if len(cycle) > 2:
                for start_idx, (i, j) in enumerate(cycle[:-2:2]):
                    start_idx = start_idx * 2
                    j = cycle[-1][1]
                    v = random_assignment[i][j]
                    if  v != 0 and v != 1:
                        return cycle[start_idx:] + [(i, j)]

            ## find next cycle element
            for i in range(n):
                v = random_assignment[i][cycle[-1][1]]
                if  v != 0 and v != 1 and i != cycle[-1][0]:
                    cycle.append((i,cycle[-1][1]))
                    break

            # horizontal next

            ## check if we can finish
            if len(cycle) > 2:
                for start_idx, (i, j) in enumerate(cycle[1:-2:2]):
                    start_idx = start_idx * 2 + 1
                    i = cycle[-1][0]
                    v = random_assignment[i][j]
                    if  v != 0 and v != 1:
                        return cycle[start_idx:] + [(i, j)]

            ## find next cycle element
            for j in range(n):
                v = random_assignment[cycle[-1][0]][j]
                if  v != 0 and v != 1 and j != cycle[-1][1]:
                    cycle.append((cycle[-1][0],j))
                    break
    def find_cycle_minima(cycle):
        turn = True
        odd_min = 1
        even_min = 1
        for i, j in cycle:
            v = random_assignment[i][j]
            if turn:
              if v < even_min:
                even_min = v
            else:
              if v < odd_min:
                odd_min = v
            turn = not turn
        return even_min, odd_min

    while True:
        cycle_start = find_start()
        if not cycle_start: break
        cycle = find_cycle(cycle_start)
        even_min, odd_min = find_cycle_minima(cycle)
        if random.uniform(0,1) < odd_min / (odd_min + even_min):
            delta = even_min
        else:
            delta = -odd_min
        for i,j in cycle[::2]:
            random_assignment[i][j] -= delta
        for i,j in cycle[1::2]:
            random_assignment[i][j] += delta
    return [l.index(Fraction(1)) for l in random_assignment]

def test_fix_random_assignment():
    f = Fraction(1)
    ra  = [[f*7/10, f*3/10, f*0   , f*0   ],
           [f*0   , f*0   , f*7/10, f*3/10],
           [f*3/10, f*0   , f*3/10, f*4/10],
           [f*0   , f*7/10, f*0   , f*3/10]]
    ra1 = [[f*7/10, f*3/10],
           [f*3/10, f*7/10]]
    ra2 = [[f*7/10, f*3/10, f*0   , f*0   ],
           [f*0   , f*0   , f*7/10, f*3/10]]
    ra2 = fill_incomplete_random_assignment(ra2)
    assert is_valid_random_assignment(ra)

def test_Collector():
    c = Collector("data.json", "keys.json")
    #c.create_keys()
    #c.write_invitation_files()
    #c.send_invitation_emails()
    #print(c.calc_assignment())

def main():
    parser = argparse.ArgumentParser()
    commands = {
            'create_keys' : lambda c: c.create_keys(),
            'write_invitation_files' : lambda c: c.write_invitation_files(),
            'send_invitation_emails' : lambda c: c.send_invitation_emails(),
            'calc_assignment' : lambda c: print(c.calc_assignment())
    }
    parser.add_argument('datafile',
            help='The file that keeps all the information.')
    parser.add_argument('keyfile',
            help='The file in which to place or read the keys (depending on the command)')
    parser.add_argument('command',
            choices=list(commands.keys()),
            help='can be one of: {}'.format(', '.join(commands.keys())),
            metavar='command')
    parser.add_argument('--really_send_emails', action='store_true', default=False)
    args = parser.parse_args()

    c = Collector(args.datafile, args.keyfile, args.really_send_emails)
    commands[args.command](c)

if __name__ == "__main__":
    main()
    #test_Collector()
    #test_fix_random_assignment()




