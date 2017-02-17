# Assign Fair

`assign_fair` is a simple script that assigns agents to objects
based on the preferences of the agents.
One possible use case is assigning topics to students, in the context of a seminar.
A certain number of topics are available and every student must present one of them in order to complete the seminar.
The students may have preferences about which topics they want to work on.

The preference that an agent submits to the algorithm is an ordered
list from most wanted to least wanted object.

`assign_fair` was developed to accommodate a very specific workflow well.
Because of that there a few unnecessary hops for other applications.

## Theory

This algorithm implements probabilistic serial [1].
The random assignment is envy free, ordinal efficient, and weak strategyproof [1].
The random assignment are the probabilities that an agent gets a certain object.

To produce a deterministic assignment the algorithm from [2] is used.

[1] Anna Bogomolnaia and Hervé Moulin. A new solution to the random assignment problem. 2001.

[2] Aanund Hylland and Richard Zeckhauser. The efficient allocation of individuals to positions. The Journal of Political Economy, Vol. 87, No. 2, 1979.

// TODO

## Usage

### Preparation

There are two CSV files necessary to use `assign\_fair`:
The CSV file entries must be separated with `;` (as it seems to be usual in Germany)
(it is trivial to patch that).

1. A CSV file describes the agents, one agent per line.
   In the following this file is named `students.csv`.
   It must have an `Email` (with this exact spelling and casing) column.
   The content of the `Email` columns doesn't have to be an actual email address,
   but all values in the Email column must be unique.
   Other columns are optional and possibly useful because the result of `assign_fair`
   often produces a copy of this file with additional columns.

   `students.csv`:
   ```
   Email
   student1@example.org
   student2@example.org
   student3@example.org
   student4@example.org
   student5@example.org
   ```

2. A CSV file that describes the topics.
   In the following this file is named `topics.csv`.
   Currently it must have the columns `Thema`, `Betreuer`, and `Email_Betreuer`.

   `topics.csv`:
   ```
   Thema;Betreuer;Email_Betreuer
   topic1;Tutor1;Tutor1@example.org
   topic2LongName;Tutor2;Tutor2@example.org
   topic3;Tutor3;Tutor3@example.org
   topic4;Tutor4;Tutor4@example.org
   topic5;Tutor5;Tutor5@example.org
   ```

   These specific columns are needed because the `topic_format` format string is:

   ```
   '"{Thema:<{Thema_max_size}s}"  {Betreuer:<{Betreuer_max_size}s}  {Email_Betreuer:<{Email_Betreuer_max_size}s}'
   ```

   (This format can be changed in the source code. It should not produce multiple lines.)

   This is a python format string as produced when formatting with the `format(**args)` method on string.
   For every object this format string must produce a unique output (i.e. No two object may result in the same string).
   The format variables are the column names and for every column name a `*_max_size`
   with the maximum length of the values in the column, so they can be aligned properly.

### Execution

#### 1. Create keys

Note: This step is just needed for a "security" measure that was found to be good enough for the purpose.

Every Student get assigned a short key (random password).
These keys are saved in a file `keys.json` and is used in the next two steps.
To use a different file name instead of `keys.json` use the `--keys` option (in this an all following steps).

```
$ python3 .\assign_fair.py students.csv topics.csv create_keys
```

This "security" measure is to make it more difficult for one student to submit preferences for an other student.
If the preference files (created in the next step) for the students are collected via email.
All attachments can be saved in the same directory without further consideration because the file name contains the key
and no other student should have easy access to that key.

In our example this resulted in:

`keys.json`:
```
[ { "email": "student5@example.org", "key": "hkdte34ddd" },
  { "email": "student4@example.org", "key": "zqxooapjil" },
  { "email": "student1@example.org", "key": "onrgeqypov" },
  { "email": "student2@example.org", "key": "14bsan3v3v" },
  { "email": "student3@example.org", "key": "vwjrocwloc" } ]
```

#### 2. Prepare

In this steps we create preference files which the students can use as a template to submit their preferences.

Note: if you want to use a key file different that `keys.json` you must specify that with the `--keys` option.

```
$ python3 assign_fair.py students.csv topics.csv prepare
```

This creates a file for every student in the directory `preferences` (can be changed with the `--pref_dir` option
(must than also be changed in the next step)).
An example file would be:

`student1@example.org.(onrgeqypov).txt`:
```
{"topic4        "  Tutor4  Tutor4@example.org}
{"topic5        "  Tutor5  Tutor5@example.org}
{"topic3        "  Tutor3  Tutor3@example.org}
{"topic1        "  Tutor1  Tutor1@example.org}
{"topic2LongName"  Tutor2  Tutor2@example.org}
```

The topics are randomized for every student separately.

Additionally a file `out.csv` (can be changed with the `--out_file` option) is produced.
It contains every column that the `students.csv` file contains and an additional column `Anhang`
containing the file name of the preference template.

`out.csv`:
```
Email;Anhang
student4@example.org;student4@example.org.(zqxooapjil).txt
student2@example.org;student2@example.org.(14bsan3v3v).txt
student1@example.org;student1@example.org.(onrgeqypov).txt
student3@example.org;student3@example.org.(vwjrocwloc).txt
student5@example.org;student5@example.org.(hkdte34ddd).txt
```

This can be used to send serial emails.

#### Collect preferences from students

Now every student somehow gets their template, reorders the topics in them so they are sorted from their favorite to least favorite.
The files are returned and saved in the preference folder.
The names of the files may not change
and within the files nothing enclosed in curly braces `{}` may change.
Just the order of the lines.
It's pretty rudimentary I know...

Because every template has a random permutation and are in the correct folder, we can just skip this step and continue with our example.

#### 3. Calculate Assignment

Now that we gathered the preferences we can apply the algorithm.
The preference files must be in the preference directory (specified with the `--pref_dir` option; defaults to `preferences`)

Note: if you want to use a key file different that `keys.json` you must specify that with the `--keys` option.

```
$ rm out.csv # there would be an error if the out file already exists (the file can also be changed with the `--out_file` option)
$ python3 assign_fair.py students.csv topics.csv calc_assignment
in 1/16
student4@example.org     0   0   8   0   8
student1@example.org     0   0   1  15   0
student2@example.org     0  12   4   0   0
student3@example.org     2   4   2   0   8
student5@example.org    14   0   1   1   0
```

The output is the probability matrix of the random assignment.
The columns (left to right) represent the topics in the same order as specified in the file `topics.csv`.
Each entry is the probability that the student got assigned the topic with the unit is given in the top left.
So in this example `student3@example.org` got `topic2` with the probability 12/16=75% and `topic3` with 4/16=25%

Additionally a file is produced (specified with the `--out_file` option; defaults to `out.csv`)
that is a modified version of `students.csv` with the additional columns of the `topic.csv`
of that topic that was ultimately assigned to that student.
This assignment is random, so running `calc_assignment` again likely produces a different result.

`out.csv`:
```
Email;Thema;Betreuer;Email_Betreuer
student4@example.org;topic5;Tutor5;Tutor5@example.org
student1@example.org;topic4;Tutor4;Tutor4@example.org
student2@example.org;topic2LongName;Tutor2;Tutor2@example.org
student3@example.org;topic3;Tutor3;Tutor3@example.org
student5@example.org;topic1;Tutor1;Tutor1@example.org
```

### More topics than students

That's okay. The excess topics that no one wants are just assigned to dummy students.
Running though the steps above again, with only 3 students yields:

```
$ python3 assign_fair.py students.csv topics.csv calc_assignment
in 1/4
student2@example.org    2  0  2  0  0
student1@example.org    2  0  0  2  0
student3@example.org    0  4  0  0  0
dummy agent             0  0  1  1  2
dummy agent             0  0  1  1  2
```

### More students than topics

That results in an error when unsung `assign_fair`.
One can however manually add dummy topics and then decide what it means to get matched with one.
Students must now rank the dummy topics alongside other topics.

### Missing preference files

If the preference file for a student doesn't exist in the preference directory when `calc_assignment` is called
they get the left over topics.
The topics that no one else wants similar to the dummy students above.
However at least one student must specify preferences.


