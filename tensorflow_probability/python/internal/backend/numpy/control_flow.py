# Copyright 2018 The TensorFlow Probability Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Numpy implementations of TensorFlow top-level control flow functions."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# Dependency imports

import tensorflow.compat.v2 as tf

from tensorflow_probability.python.internal.backend.numpy import _utils as utils


__all__ = [
    'no_op',
    'while_loop',
    # 'case',
    # 'cond',
    # 'dynamic_partition',
    # 'dynamic_stitch',
    # 'map_fn',
    # 'scan',
]


def _no_op(_):
  pass


def _while_loop(cond, body, loop_vars,
                shape_invariants=None, parallel_iterations=10,  # pylint: disable=unused-argument
                back_prop=True, swap_memory=False,  # pylint: disable=unused-argument
                maximum_iterations=None, name=None):  # pylint: disable=unused-argument
  i = 0
  while (cond(*loop_vars) and
         (maximum_iterations is None or i < maximum_iterations)):
    loop_vars = body(*loop_vars)
    i += 1
  return loop_vars

# --- Begin Public Functions --------------------------------------------------

no_op = utils.copy_docstring(
    tf.no_op,
    _no_op)

while_loop = utils.copy_docstring(
    tf.while_loop,
    _while_loop)
