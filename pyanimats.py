#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pyanimats.py

"""
PyAnimats
~~~~~~~~~
Evolve animats.

Command-line options override the parameters given in the experiment file.

Usage:
    pyanimats.py <path/to/output_dir> <path/to/experiment.yml> [options]
    pyanimats.py -h | --help
    pyanimats.py -v | --version
    pyanimats.py list

Options:
    -h --help                 Show this
    -v --version              Show version
       --list-fitness         List available fitness functions
    -r --rng-seed=INT         Random number generator seed
    -t --snapshot=INT         Snapshot interval (minutes)
    -s --status-interval=INT  Status-printing interval (generations)
    -o --min-snapshots=INT    Minimum number of snapshots to take
    -l --log-interval=INT     Logbook recording interval (generations)
    -i --num-samples=INT      Number of animats to sample from evolution
    -f --fitness=FUNC         Fitness function
    -n --num-gen=NGEN         Number of generations to simulate
    -p --pop-size=INT         Population size
                                (0 saves entire lineage)
    -g --init-genome=PATH     Path to a lineage file for an intial genome
    -j --jumpstart=INT        Begin with this many start codons
    -a --all-lineages         Save lineages of entire final population
       --num-sensors=INT      The number of sensors in an animat
       --num-hidden=INT       The number of hidden units in an animat
       --num-motors=INT       The number of motors in an animat
       --world-width=INT      The width of the animats' environment
       --world-height=INT     The height of the animats' environment
    -m --mut-prob=FLOAT       Point mutation probability
       --dup-prob=FLOAT       Duplication probability
       --del-prob=FLOAT       Deletion probability
       --min-dup-del=INT      Minimum length of duplicated/deleted genome part
       --max-dup-del=INT      Maximum length of duplicated/deleted genome part
       --min-length=INT       Minimum genome length
       --max-length=INT       Maximum genome length
       --profile=PATH         Profile performance and store results at PATH
"""

__version__ = '0.0.23'

import config
import cProfile
import json
import os
import pickle
import random
from pprint import pprint
from time import time

import numpy as np
from deap import base, tools
from docopt import docopt

import configure
import fitness_functions
import utils
from experiment import Experiment
from animat import Animat


MINUTES = 60


def select(animats, k):
    """Select *k* animats from the given list of animats using the
    variant of roulette-wheel selection used in the old C++ code.

    :param animats: A list of animats to select from.
    :param k: The number of animats to select.
    :returns: A list of selected animats.

    This function uses the :func:`~random.random` function from the built-in
    :mod:`random` module."""
    max_fitness = max([animat.fitness.value for animat in animats])
    chosen = []
    for i in range(k):
        done = False
        while not done:
            candidate = random.choice(animats)
            done = random.random() <= (candidate.fitness.value /
                                       max_fitness)
        chosen.append(candidate)
    return chosen


def mutate(animat):
    animat.mutate()
    return (animat,)
mutate.__doc__ = Animat.mutate.__doc__


def main(arguments):

    # Handle arguments
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    # TODO make this an option for -h?
    # Print available fitness functions and their descriptions.
    if arguments['--list-fitness']:
        fitness_functions.print_functions()
        return

    # Final output and snapshots will be written here.
    OUTPUT_DIR = arguments['<path/to/output_dir>']

    # Ensure profile directory exists and set profile flag.
    PROFILING = False
    profile_filepath = arguments['--profile']
    if profile_filepath:
        PROFILING = True
        utils.ensure_exists(os.path.dirname(profile_filepath))

    # Map CLI options to experiment parameter names and types.
    cli_opt_to_param = {
        '--rng-seed':        ('rng_seed', int),
        '--snapshot':        ('snapshot_frequency', int),
        '--status-interval': ('status_interval', int),
        '--min-snapshots':   ('min_snapshots', int),
        '--log-interval':    ('log_interval', int),
        '--num-samples':     ('num_samples', int),
        '--fitness':         ('fitness_function', str),
        '--num-gen':         ('ngen', int),
        '--pop-size':        ('popsize', int),
        '--init-genome':     ('init_genome', str),
        '--jumpstart':       ('init_start_codons', int),
        '--num-sensors':     ('num_sensors', int),
        '--num-hidden':      ('num_hidden', int),
        '--num-motors':      ('num_motors', int),
        '--world-width':     ('world_width', int),
        '--world-height':    ('world_height', int),
        '--mut-prob':        ('mutation_prob', float),
        '--dup-prob':        ('duplication_prob', float),
        '--del-prob':        ('deletion_prob', float),
        '--min-dup-del':     ('min_dup_del_width', int),
        '--max-dup-del':     ('min_dup_del_width', int),
        '--min-length':      ('min_genome_length', int),
        '--max-length':      ('max_genome_length', int),
    }
    # Load the experiment object, overriding if necessary with CLI options.
    cli_overrides = {param[0]: param[1](arguments[opt])
                     for opt, param in cli_opt_to_param.items()
                     if arguments[opt] is not None}
    experiment = Experiment(filepath=arguments['<path/to/experiment.yml>'],
                            override=cli_overrides)

    # Get the minimum number of snapshots to be taken.
    MIN_SNAPSHOTS = experiment.min_snapshots

    # Get the interval at which to take snapshots.
    SNAPSHOT_TIME_INTERVAL = experiment.snapshot_frequency * MINUTES
    if SNAPSHOT_TIME_INTERVAL <= 0:
        SNAPSHOT_TIME_INTERVAL = float('inf')

    # Snapshots will be written to disk at this interval.
    if experiment.min_snapshots <= 0:
        SNAPSHOT_GENERATION_INTERVAL = float('inf')
    else:
        SNAPSHOT_GENERATION_INTERVAL = (experiment.ngen //
                                        experiment.min_snapshots)

    # Whether or not to save every animat in the population, or just the
    # fittest one.
    SAVE_ALL_LINEAGES = arguments['--all-lineages']


    # Helper functions
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def save_data(output_dir, gen, config, pop, logbook, hof, elapsed):
        # Ensure output directory exists.
        utils.ensure_exists(output_dir)
        # Collect lineages.
        if SAVE_ALL_LINEAGES:
            to_save = pop
        else:
            to_save = [max(pop, key=lambda animat: animat.fitness.value)]
        step = (1 if experiment.num_samples <= 0
                else max(gen // experiment.num_samples, 1))
        lineages = tuple(tuple(animat.lineage())[::step] for animat in to_save)
        # Save config and metadata as JSON.
        data_json = {
            'config': configure.get_dict(),
            'metadata': {
                'elapsed': round(elapsed, 2),
                'version': __version__
            }
        }
        for key in data_json:
            with open(os.path.join(output_dir, str(key) + '.json'), 'w') as f:
                json.dump(data_json[key], f, indent=2, separators=(',', ': '))
        # Pickle everything else.
        data_pickle = {
            'lineages': lineages,
            'logbook': logbook,
            'hof': [animat._c_animat for animat in hof],
        }
        for key in data_pickle:
            with open(os.path.join(output_dir, str(key) + '.pkl'), 'wb') as f:
                pickle.dump(data_pickle[key], f)

    # Setup
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    toolbox = base.Toolbox()

    # Register the various genetic algorithm components to the toolbox.
    toolbox.register('animat', Animat, experiment, experiment.init_genome)
    toolbox.register('population', tools.initRepeat, list, toolbox.animat)
    toolbox.register('evaluate',
                     fitness_functions.__dict__[experiment.fitness_function])
    toolbox.register('select', select)
    toolbox.register('mutate', mutate)

    # Create statistics trackers.
    fitness_stats = tools.Statistics(key=lambda animat: animat.fitness.raw)
    fitness_stats.register('max', np.max)

    real_fitness_stats = tools.Statistics(key=lambda animat: animat.fitness.value)
    real_fitness_stats.register('max', np.max)

    correct_stats = tools.Statistics(key=lambda animat: (animat.correct,
                                                         animat.incorrect))
    correct_stats.register('correct', lambda x: np.max(x, 0)[0])
    correct_stats.register('incorrect', lambda x: np.max(x, 0)[1])

    # Stats objects for alternate matching measures.
    alt_fitness_stats = tools.Statistics(key=lambda animat: animat.alt_fitness)
    alt_fitness_stats.register('weighted', lambda x: np.max(x, 0)[0])
    alt_fitness_stats.register('unweighted', lambda x: np.max(x, 0)[1])

    # Initialize a MultiStatistics object for convenience that allows for only
    # one call to `compile`.
    if experiment.fitness_function == 'mat':
        mstats = tools.MultiStatistics(correct=correct_stats,
                                       fitness=fitness_stats,
                                       real_fitness=real_fitness_stats,
                                       alt_fitness=alt_fitness_stats)
    else:
        mstats = tools.MultiStatistics(correct=correct_stats,
                                       fitness=fitness_stats,
                                       real_fitness=real_fitness_stats)

    # Initialize logbooks and hall of fame.
    logbook = tools.Logbook()
    hall_of_fame = tools.HallOfFame(maxsize=experiment.popsize)

    def print_status(line, time):
        print('[Seed {}] '.format(experiment.rng_seed), end='')
        print(line, utils.compress(time))

    print('\nSimulating {} generations...\n'.format(experiment.ngen))

    if PROFILING:
        pr = cProfile.Profile()
        pr.enable()
    sim_start = time()

    # Simulation
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def multi_fit_evaluate(pop, gen):
        fitnesses = toolbox.map(toolbox.evaluate, pop)
        for animat, fitness in zip(pop, fitnesses):
            animat.fitness.set(fitness[0])
            animat.alt_fitness = fitness[1:]

    def single_fit_evaluate(pop, gen):
        fitnesses = toolbox.map(toolbox.evaluate, pop)
        for animat, fitness in zip(pop, fitnesses):
            animat.fitness.set(fitness)

    evaluate = (multi_fit_evaluate if experiment.fitness_function == 'mat'
                else single_fit_evaluate)

    def record(pop, gen):
        hall_of_fame.update(pop)
        if gen % experiment.log_interval == 0:
            record = mstats.compile(pop)
            logbook.record(gen=gen, **record)

    def process_gen(pop, gen):
        # Selection.
        pop = toolbox.select(pop, len(pop))
        # Cloning.
        offspring = [toolbox.clone(animat) for animat in pop]
        for animat in offspring:
            # Tag offspring with new generation number.
            animat.gen = gen
        # Variation.
        for i in range(len(offspring)):
            toolbox.mutate(offspring[i])
            offspring[i].parent = pop[i]
        # Evaluation.
        evaluate(offspring, gen)
        # Recording.
        record(offspring, gen)
        return offspring

    # Create initial population.
    population = toolbox.population(n=experiment.popsize)

    log_duration_start = time()
    # Evaluate the initial population.
    evaluate(population, 0)
    # Record stats for initial population.
    record(population, 0)
    # Print first lines of logbook.
    first_lines = str(logbook).split('\n')
    header_lines = ['[Seed {}] '.format(experiment.rng_seed) + l
                    for l in first_lines[:-1]]
    print('\n'.join(header_lines))
    print_status(first_lines[-1], time() - log_duration_start)

    log_duration_start = time()
    snap_duration_start = time()
    snapshot = 1
    for gen in range(1, experiment.ngen + 1):
        # Evolution.
        population = process_gen(population, gen)
        # Reporting.
        if gen % experiment.status_interval == 0:
            # Get time since last report was printed.
            log_duration_end = time()
            print_status(logbook.__str__(startindex=gen),
                         log_duration_end - log_duration_start)
            log_duration_start = time()
        # Snapshotting.
        current_time = time()
        if (current_time - snap_duration_start >= SNAPSHOT_TIME_INTERVAL
                or gen % SNAPSHOT_GENERATION_INTERVAL == 0):
            print('[Seed {}] –\tRecording snapshot {}... '.format(
                experiment.rng_seed, snapshot), end='')
            dirname = os.path.join(OUTPUT_DIR,
                                   'snapshot-{}-gen-{}'.format(snapshot, gen))
            save_data(dirname, gen, config=configure.get_dict(),
                      pop=population, logbook=logbook, hof=hall_of_fame,
                      elapsed=(current_time - sim_start))
            print('done.')
            snapshot += 1
            snap_duration_start = time()

    # Finish
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    sim_end = time()
    if PROFILING:
        pr.disable()
        pr.dump_stats(profile_filepath)

    print('\nSimulated {} generations in {}.'.format(
        experiment.ngen, utils.compress(sim_end - sim_start)))

    # Write final results to disk.
    save_data(OUTPUT_DIR, gen, config=configure.get_dict(), pop=population,
              logbook=logbook, hof=hall_of_fame, elapsed=(sim_end - sim_start))


if __name__ == '__main__':
    # Get command-line arguments from docopt.
    arguments = docopt(__doc__, version=__version__)
    main(arguments)
