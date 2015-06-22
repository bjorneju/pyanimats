#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fitness_functions.py

"""
Fitness functions for driving animat evolution.
"""

import textwrap
wrapper = textwrap.TextWrapper(width=80)

from functools import wraps
import math
import numpy as np
from sklearn.metrics import mutual_info_score
import pyphi

from parameters import params


# A registry of available fitness functions
functions = {}
# Mapping from parameter values to descriptive names
LaTeX_NAMES = {
    'mi': 'Mutual\ Information',
    'nat': 'Correct\ Trials',
    'ex': 'Extrinsic\ cause\ information',
    'sp': '\sum\\varphi',
}


def _register(f):
    """Register a fitness function to the directory."""
    functions[f.__name__] = f.__doc__
    return f


def print_functions():
    """Display a list of available fitness functions with their
    descriptions."""
    for name, doc in functions.items():
        print('\n' + name + '\n    ' + doc)
    print('\n' + wrapper.fill(
        'NB: In order to make selection pressure more even, the fitness '
        'function used in the selection algorithm is transformed so that it '
        'is exponential. This is accomplished by using the ``FITNESS_BASE`` '
        'parameter as the base and the fitnesses descibed above as the '
        'exponent.'))
    print('')


# Helper functions
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def _most_common_states(game, n=False):
    # Get the array in 2D form.
    game = game.reshape(-1, game.shape[-1])
    # Lexicographically sort.
    sorted_game = game[np.lexsort(game.T), :]
    # Get the indices where a new state appears.
    diff_idx = np.where(np.any(np.diff(sorted_game, axis=0), 1))[0]
    # Get the unique states.
    unique_states = [sorted_game[i] for i in diff_idx] + [sorted_game[-1]]
    # Get the number of occurences of each unique state (the -1 is needed at
    # the beginning, rather than 0, because of fencepost concerns).
    counts = np.diff(np.insert(diff_idx, 0, -1))
    # Return all by default.
    if n is False or n > counts.size:
        n = counts.size
    # Return the (row, count) pairs sorted by count.
    return list(sorted(zip(unique_states, counts), key=lambda x: x[1],
                       reverse=True))[:n]


def _average_over_game_states(func, n=False):
    """A decorator that takes an animat and applies a function to every unique
    state the animat goes into during a game and returns the average.

    The wrapped function must take an animat, state, and count and return a
    number.

    The optional parameter ``n`` can be set to consider only the ``n`` most
    common states."""
    @wraps(func)
    def wrapper(ind):
        game = ind.play_game()
        unique_states_and_counts = _most_common_states(game, n=n)
        sums = np.empty(len(unique_states_and_counts))
        for i, (state, count) in enumerate(unique_states_and_counts):
            sums[i] = func(ind, state, count)
        return sums.mean()
    return wrapper


# Natural fitness
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@_register
def nat(ind):
    """Natural: Animats are evaluated based on the number of game trials they
    successfully complete."""
    ind.play_game()
    return ind.animat.correct


# Mutual information
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def _bitlist(i, padlength):
    """Return a list of the bits of an integer, padded up to ``padlength``."""
    return list(map(int, bin(i)[2:].zfill(padlength)))


NUM_SENSOR_STATES = 2**params.NUM_SENSORS
NUM_MOTOR_STATES = 2**params.NUM_MOTORS
SENSOR_MOTOR_STATES = [
    ((i, j), _bitlist(i, params.NUM_SENSORS) + _bitlist(j, params.NUM_MOTORS))
    for i in range(NUM_SENSOR_STATES) for j in range(NUM_MOTOR_STATES)
]
NAT_TO_BIT_CONVERSION_FACTOR = 1 / math.log(2)


@_register
def mi(ind):
    """Mutual information: Animats are evaluated based on the mutual
    information between their sensors and motors."""
    # Play the game and get the state transitions for each trial.
    game = ind.play_game()
    # The contingency matrix has a row for every sensors state and a column for
    # every motor state.
    contingency = np.zeros([NUM_SENSOR_STATES, NUM_MOTOR_STATES])
    # Get only the sensor and motor states.
    sensor_motor = np.concatenate([game[:, :, :params.NUM_SENSORS],
                                   game[:, :, -params.NUM_MOTORS:]], axis=2)
    # Count!
    for idx, state in SENSOR_MOTOR_STATES:
        contingency[idx] = (sensor_motor == state).all(axis=2).sum()
    # Calculate mutual information in nats.
    mi_nats = mutual_info_score(None, None, contingency=contingency)
    # Convert from nats to bits and return.
    return mi_nats * NAT_TO_BIT_CONVERSION_FACTOR


# Extrinsic cause information
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@_register
@_average_over_game_states
def ex(ind, state, count):
    """Extrinsic cause information: Animats are evaluated based on the sum of φ
    for concepts that are “about” the sensors. This sum is averaged
    over every unique state the animat goes into during a game."""
    subsystem = ind.brain_and_sensors(state)

    hidden = subsystem.indices2nodes(params.HIDDEN_INDICES)
    sensors = subsystem.indices2nodes(params.SENSOR_INDICES)

    mechanisms = tuple(pyphi.utils.powerset(hidden))
    purviews = tuple(pyphi.utils.powerset(sensors))

    mice = [subsystem.core_cause(mechanism, purviews=purviews)
            for mechanism in mechanisms]
    return sum(m.phi for m in mice)


# Sum of small-phi
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@_register
@_average_over_game_states
def sp(ind, state, count):
    """Sum of φ: Animats are evaluated based on the sum of φ for all the
    concepts of the animat's hidden units, or “brain”. This sum is averaged
    over every unique state the animat goes into during a game."""
    subsystem = ind.brain_and_sensors(state)
    brain_mechanisms = pyphi.utils.powerset(params.HIDDEN_INDICES)
    constellation = pyphi.compute.constellation(
        subsystem, mechanism_indices_to_check=brain_mechanisms)
    return sum(concept.phi for concept in constellation)
