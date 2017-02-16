#!/usr/bin/env python3

import json
import csv
import argparse
import re
import os
import random
import copy
from fractions import Fraction
from functools import reduce

topic_format = '"{Thema:<{Thema_max_size}s}"  {Betreuer:<{Betreuer_max_size}s}  {Email_Betreuer:<{Email_Betreuer_max_size}s}'
csv_delimiter = ';'

def gen_a_key():
    key_chars = "abcdefghijklmnopqrstuvwxyz012345" # 32 values
    return ''.join([key_chars[r & 31] for r in os.urandom(10)])

def personalize(person, string):
    for key, value in person.items():
        string = re.sub("{" + key + "}", value, string)
    return string

def read_json_file(filename):
    with open(filename, 'tr') as f:
        return json.loads(f.read())

def merge_dicts(a, b):
    tmp = a.copy()
    tmp.update(b)
    return tmp


def lcm(vals):
    def gcd(a, b):
        while b != 0:
            a, b = b, a % b
        return a
    def lcm_single(a, b):
        return a * b // gcd(a, b)
    return reduce(lcm_single, vals)

class Collector():
    def __init__(self, people_csv, topics_csv, key_file, pref_dir, out_file):
        self.pref_dir = pref_dir
        self.out_file = out_file
        # the ordering of the people and topic elements is important b/c later only indecces are used
        with open(people_csv, 'tr') as f:
            reader = csv.DictReader(f, delimiter=csv_delimiter)
            self.people_dict = {row['Email']: row for row in reader}
            self.people_fieldnames = reader.fieldnames
        self.people = list(self.people_dict.keys())
        assert len(self.people) == len(set(self.people))
        with open(topics_csv, 'r') as f:
            reader = csv.DictReader(f, delimiter=csv_delimiter)
            self.topic_fieldnames = reader.fieldnames
            self.topics_csv = [t for t in reader]
            fmt_dict = {
                    k + "_max_size": max(
                        map(lambda i: len(i[k]), self.topics_csv)
                    )
                    for k in reader.fieldnames
                }
            self.topics = [
                    topic_format.format(**merge_dicts(t, fmt_dict))
                    for t in self.topics_csv
                ]
        assert not any(['{' in t or '}' in t for t in self.topics])
        assert len(self.topics) == len(set(self.topics))
        assert len(self.people) <= len(self.topics)
        # we correlate the index for a topic to the string it produces (we need just that to retrive the preferences)
        self.key_file = key_file

    def create_keys(self):
        if os.path.isfile(self.key_file):
            raise Exception("Want to create key file but it allready exists.")
        keys = set()
        while len(keys) < len(self.people):
            keys.add(gen_a_key())
        keys = list(keys)

        keys = [{'email': person_email, 'key': key}
                for person_email, key in zip(self.people, keys)]
        with open(self.key_file, 'tx') as f:
            f.write(json.dumps(keys, indent=2))

    def get_invitation_attachment(self, key_entry):
        topics = ['{'+t+'}' for t in self.topics]
        random.shuffle(topics)
        txt = "\n".join(topics)
        filename = "{}.({}).txt".format(key_entry['email'], key_entry['key'])
        return (txt, filename)

    def write_invitation_files(self):
        if not os.path.isfile(self.key_file):
            raise Exception("cannot find key file")
        keys = read_json_file(self.key_file)
        os.makedirs(self.pref_dir, exist_ok=True)
        new_csv = copy.deepcopy(self.people_dict)
        for k in keys:
            (txt, filename) = self.get_invitation_attachment(k)
            new_csv[k['email']]['Anhang'] = filename
            with open(os.path.join(self.pref_dir, filename), 'tx') as f:
                f.write(txt)
        with open(self.out_file, 'tx') as f:
            writer = csv.DictWriter(f,
                    self.people_fieldnames + ['Anhang'], delimiter=csv_delimiter
                )
            writer.writeheader()
            for row in new_csv.values():
                writer.writerow(row)


    topic_split_regex = re.compile('(?:^|})[^{}]*(?:{|$)')
    def extract_preferences(self, filename):
        with open(filename, 'tr') as f:
            txt = f.read().strip()
        topics = self.topic_split_regex.split(txt)[1:-1]
        preference_list = []
        for t in topics:
            if t not in self.topics:
                raise Exception("invalid topic in '{filename}': {topic}"
                        .format(filename=filename, topic=t))
            preference_list.append(self.topics.index(t))
        if not len(self.topics) == len(preference_list):
            print("{} is incomplete; some topics are missing".format(filename))
            for i,t in enumerate(self.topics):
                if t not in preference_list:
                    print("'{}' is missing in '{}'".format(t, filename))
                    preference_list.append(i)
        return preference_list

    def retrive_preferences(self):
        if not os.path.isfile(self.key_file):
            raise Exception("cannot find key file")
        keys = read_json_file(self.key_file)
        prefs = {}
        for filename in [f for f in os.listdir(self.pref_dir)
                           if f.endswith('.txt')]:
            matching_keys = [k for k in keys if '('+k['key']+')' in filename]
            if len(matching_keys) < 1:
                raise Exception("file {} doesn't contain any known key"
                        .format(filename))
            if len(matching_keys) > 1:
                raise Exception("file {} doesn't contain more than one known key"
                        .format(filename))
            k = matching_keys[0]
            prefs[k['email']] = self.extract_preferences(
                    os.path.join(self.pref_dir, filename)
                )
        return prefs

    def calc_assignment(self):
        prefs_dict = self.retrive_preferences()
        # sort the preferences correctly, now we just use the index to identify to person
        index_person_map = {}
        prefs_list = []
        index_with_pref = 0
        index_without_pref = len(prefs_dict)
        for person_email in self.people:
            if person_email in prefs_dict:
                prefs_list.append(prefs_dict[person_email])
                index_person_map[index_with_pref] = person_email
                index_with_pref += 1
            else:
                print("{}: no preferences where found".format(person_email))
                index_person_map[index_without_pref] = person_email
                index_without_pref += 1
        random_assignment = probablisitic_serial_assignmnet(prefs_list)
        random_assignment = fill_incomplete_random_assignment(random_assignment)
        assert is_valid_random_assignment(random_assignment)

        longest_email = max(map(lambda i: len(i), self.people_dict.keys()))
        denominator = lcm([lcm(map(lambda i: i.denominator, a)) for a in random_assignment])
        print("in 1/{}".format(denominator))
        def print_ra_line(email, person_idx):
            print("{:<{}s}  {}".format(email, longest_email,
                    ''.join([
                        "  {val:>{max_len}}".format(
                            val=(v * denominator).numerator,
                            max_len=len(str(denominator))
                        )
                        for v in random_assignment[person_idx]
                    ])
                ))
        for person_idx in range(len(self.people_dict)):
            email = index_person_map[person_idx]
            print_ra_line(email, person_idx)
        for person_idx in range(len(self.people_dict), len(random_assignment)):
            print_ra_line("dummy person", person_idx)

        deterministic_assignment = fix_random_assignmnet(random_assignment)

        new_csv = []
        for person_idx, assigned_topic_idx in enumerate(deterministic_assignment):
            if person_idx < len(index_person_map):
                new_csv.append(merge_dicts(
                        self.people_dict[index_person_map[person_idx]],
                        self.topics_csv[assigned_topic_idx]
                    ))
        with open(self.out_file, 'tx') as f:
            new_fieldnames = self.people_fieldnames + self.topic_fieldnames
            writer = csv.DictWriter(f, new_fieldnames, delimiter=csv_delimiter)
            writer.writeheader()
            for row in new_csv:
                writer.writerow(row)

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
        random_assignment.append(copy.deepcopy(new_topics))
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
    eaten_per_person_per_topic = [
            [Fraction(0) for _ in range(num_topics)]
            for _ in range(num_people)
        ]

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
    """
python assign_fair.py Seminar_BSc_SS_16.csv Themen_Seminar_BSc_SS_16.csv create_keys
python assign_fair.py Seminar_BSc_SS_16.csv Themen_Seminar_BSc_SS_16.csv prepare
python assign_fair.py Seminar_BSc_SS_16.csv Themen_Seminar_BSc_SS_16.csv calc_assignment --out_file out2.csv
    """
    parser = argparse.ArgumentParser()

    commands = {
            'create_keys' : lambda c: c.create_keys(),
            'prepare' : lambda c: c.write_invitation_files(),
            'calc_assignment' : lambda c: c.calc_assignment()
    }
    parser.add_argument('people_csv',
            help='information about the people. must have "Email" collum.')
    parser.add_argument('topics_csv',
            help='topics file: one topic per line.')
    parser.add_argument('command',
            choices=list(commands.keys()),
            help='can be one of: {}'.format(', '.join(commands.keys())),
            metavar='command')
    parser.add_argument('--keys', default='keys.json',
            help='The file in which to place or read the keys (depending on the command). Default is "keys.json"')
    parser.add_argument('--pref_dir', default='preferences',
            help='the directory in wich to place and read from the preference files. Default is "preferences"')
    parser.add_argument('--out_file', default='out.csv')
    args = parser.parse_args()

    c = Collector(args.people_csv, args.topics_csv, args.keys, args.pref_dir, args.out_file)
    commands[args.command](c)

if __name__ == "__main__":
    main()
    #test_Collector()
    #test_fix_random_assignment()




