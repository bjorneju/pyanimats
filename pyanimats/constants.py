#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# constants.py

"""
Container for package-level constants.
"""

import math
import random

from . import c_animat

HMM_GATE = 'hmm'
LINEAR_THRESHOLD_GATE = 'lt'
MIN_BODY_LENGTH = c_animat.MIN_BODY_LENGTH
DEFAULT_RNG = random.Random()
NAT_TO_BIT_CONVERSION_FACTOR = 1 / math.log(2)
HIT_TYPE = {c_animat.CORRECT_CATCH: 'CORRECT_CATCH',
            c_animat.WRONG_CATCH: 'WRONG_CATCH',
            c_animat.CORRECT_AVOID: 'CORRECT_AVOID',
            c_animat.WRONG_AVOID: 'WRONG_AVOID'}

PRECISION = 4

MINUTES = 60
HOURS = 60 * MINUTES
DAYS = 24 * HOURS
WEEKS = 7 * DAYS
