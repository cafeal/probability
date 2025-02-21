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
"""Utilities for testing TFP code."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import contextlib
import os

from absl import flags
from absl import logging
from absl.testing import parameterized
import numpy as np
import six
import tensorflow.compat.v1 as tf1
import tensorflow.compat.v2 as tf
from tensorflow_probability.python.internal import dtype_util
from tensorflow_probability.python.internal import test_combinations
from tensorflow_probability.python.internal.backend.numpy import ops
from tensorflow_probability.python.util.seed_stream import SeedStream
from tensorflow.python.eager import context  # pylint: disable=g-direct-tensorflow-import
from tensorflow.python.ops import gradient_checker_v2  # pylint: disable=g-direct-tensorflow-import


__all__ = [
    'numpy_disable_gradient_test',
    'jax_disable_variable_test',
    'jax_disable_test_missing_functionality',
    'test_all_tf_execution_regimes',
    'test_graph_and_eager_modes',
    'test_seed',
    'test_seed_stream',
    'DiscreteScalarDistributionTestHelpers',
    'TestCase',
    'VectorDistributionTestHelpers',
]


# Flags for controlling test_teed behavior.
flags.DEFINE_bool('vary_seed', False,
                  ('Whether to vary the PRNG seed unpredictably.  '
                   'With --runs_per_test=N, produces N iid runs.'))

flags.DEFINE_string('fixed_seed', None,
                    ('PRNG seed to initialize every test with.  '
                     'Takes precedence over --vary-seed when both appear.'))


class TestCase(tf.test.TestCase, parameterized.TestCase):
  """Class to provide TensorFlow Probability specific test features."""

  def maybe_static(self, x, is_static):
    """If `not is_static`, return placeholder_with_default with unknown shape.

    Args:
      x: A `Tensor`
      is_static: a Python `bool`; if True, x is returned unchanged. If False, x
        is wrapped with a tf1.placeholder_with_default with fully dynamic shape.

    Returns:
      maybe_static_x: `x`, possibly wrapped with in a
      `placeholder_with_default` of unknown shape.
    """
    if is_static:
      return x
    else:
      return tf1.placeholder_with_default(x, shape=None)

  def assertAllFinite(self, a):
    """Assert that all entries in a `Tensor` are finite.

    Args:
      a: A `Tensor` whose entries are checked for finiteness.
    """
    is_finite = np.isfinite(self._GetNdArray(a))
    all_true = np.ones_like(is_finite, dtype=np.bool)
    self.assertAllEqual(all_true, is_finite)

  def assertAllPositiveInf(self, a):
    """Assert that all entries in a `Tensor` are equal to positive infinity.

    Args:
      a: A `Tensor` whose entries must be verified as positive infinity.
    """
    is_positive_inf = np.isposinf(self._GetNdArray(a))
    all_true = np.ones_like(is_positive_inf, dtype=np.bool)
    self.assertAllEqual(all_true, is_positive_inf)

  def assertAllNegativeInf(self, a):
    """Assert that all entries in a `Tensor` are negative infinity.

    Args:
      a: A `Tensor` whose entries must be verified as negative infinity.
    """
    is_negative_inf = np.isneginf(self._GetNdArray(a))
    all_true = np.ones_like(is_negative_inf, dtype=np.bool)
    self.assertAllEqual(all_true, is_negative_inf)

  def assertAllNan(self, a):
    """Assert that every entry in a `Tensor` is NaN.

    Args:
      a: A `Tensor` whose entries must be verified as NaN.
    """
    is_nan = np.isnan(self._GetNdArray(a))
    all_true = np.ones_like(is_nan, dtype=np.bool)
    self.assertAllEqual(all_true, is_nan)

  def assertAllNotNone(self, a):
    """Assert that no entry in a collection is None.

    Args:
      a: A Python iterable collection, whose entries must be verified as not
      being `None`.
    """
    each_not_none = [x is not None for x in a]
    if all(each_not_none):
      return

    msg = (
        'Expected no entry to be `None` but found `None` in positions {}'
        .format([i for i, x in enumerate(each_not_none) if not x]))
    raise AssertionError(msg)

  def assertAllIs(self, a, b):
    """Assert that each element of `a` `is` `b`.

    Args:
      a: A Python iterable collection, whose entries must be elementwise `is b`.
      b: A Python iterable collection, whose entries must be elementwise `is a`.
    """
    if len(a) != len(b):
      raise AssertionError(
          'Arguments `a` and `b` must have the same number of elements '
          'but found len(a)={} and len(b)={}.'.format(len(a), len(b)))
    each_is = [a is b for a, b in zip(a, b)]
    if all(each_is):
      return
    msg = (
        'For each element expected `a is b` but found `not is` in positions {}'
        .format([i for i, x in enumerate(each_is) if not x]))
    raise AssertionError(msg)

  def compute_max_gradient_error(self, f, args, delta=1e-3):
    """Wrapper around TF's gradient_checker_v2.

    `gradient_checker_v2` depends on there being a default session, but our test
    setup, using test_combinations, doesn't run the test function under a global
    `self.test_session()` context. Thus, when running
    `gradient_checker_v2.compute_gradient`, we need to ensure we're in a
    `self.test_session()` context when not in eager mode. This function bundles
    up the relevant logic, and ultimately returns the max error across autodiff
    and finite difference gradient calculations.

    Args:
      f: callable function whose gradient to compute.
      args: Python `list` of independent variables with respect to which to
      compute gradients.
      delta: floating point value to use for finite difference calculation.

    Returns:
      err: the maximum error between all components of the numeric and
      autodiff'ed gradients.
    """
    def _compute_error():
      return gradient_checker_v2.max_error(
          *gradient_checker_v2.compute_gradient(f, x=args, delta=delta))
    if tf.executing_eagerly():
      return _compute_error()
    else:
      # Make sure there's a global default session in graph mode.
      with self.test_session():
        return _compute_error()


@contextlib.contextmanager
def _tf_function_mode_context(tf_function_mode):
  """Context manager controlling `tf.function` behavior (enabled/disabled).

  Before activating, the previously set mode is stored. Then the mode is changed
  to the given `tf_function_mode` and control yielded back to the caller. Upon
  exiting the context, the mode is returned to its original state.

  Args:
    tf_function_mode: a Python `str`, either 'no_tf_function' or ''.
    If '', `@tf.function`-decorated code behaves as usual (ie, a
    background graph is created). If 'no_tf_function', `@tf.function`-decorated
    code will behave as if it had not been `@tf.function`-decorated. Since users
    will be able to do this (e.g., to debug library code that has been
    `@tf.function`-decorated), we need to ensure our tests cover the behavior
    when this is the case.

  Yields:
    None
  """
  if tf_function_mode not in ['', 'no_tf_function']:
    raise ValueError(
        'Only allowable values for tf_function_mode_context are "" '
        'and "no_tf_function"; but got "{}"'.format(tf_function_mode))
  original_mode = tf.config.experimental_functions_run_eagerly()
  try:
    tf.config.experimental_run_functions_eagerly(tf_function_mode ==
                                                 'no_tf_function')
    yield
  finally:
    tf.config.experimental_run_functions_eagerly(original_mode)


class EagerGraphCombination(test_combinations.TestCombination):
  """Run the test in Graph or Eager mode.  Graph is the default.

  The optional `mode` parameter controls the test's execution mode.  Its
  accepted values are "graph" or "eager" literals.
  """

  def context_managers(self, kwargs):
    # TODO(isaprykin): Switch the default to eager.
    mode = kwargs.pop('mode', 'graph')
    if mode == 'eager':
      return [context.eager_mode()]
    elif mode == 'graph':
      return [tf1.Graph().as_default(), context.graph_mode()]
    else:
      raise ValueError(
          '`mode` must be "eager" or "graph". Got: "{}"'.format(mode))

  def parameter_modifiers(self):
    return [test_combinations.OptionalParameter('mode')]


class ExecuteFunctionsEagerlyCombination(test_combinations.TestCombination):
  """A `TestCombinationi` for enabling/disabling `tf.function` execution modes.

  For more on `TestCombination`, check out
  'tensorflow/python/framework/test_combinations.py' in the TensorFlow code
  base.

  This `TestCombination` supports two values for the `tf_function` combination
  argument: 'no_tf_function' and ''. The mode switching is performed using
  `tf.experimental_run_functions_eagerly(mode)`.
  """

  def context_managers(self, kwargs):
    mode = kwargs.pop('tf_function', '')
    return [_tf_function_mode_context(mode)]

  def parameter_modifiers(self):
    return [test_combinations.OptionalParameter('tf_function')]


def test_all_tf_execution_regimes(test_class_or_method=None):
  """Decorator for generating a collection of tests in various contexts.

  Must be applied to subclasses of `parameterized.TestCase` (from
  `absl/testing`), or a method of such a subclass.

  When applied to a test method, this decorator results in the replacement of
  that method with a collection of new test methods, each executed under a
  different set of context managers that control some aspect of the execution
  model. This decorator generates three test scenario combinations:

    1. Eager mode with `tf.function` decorations enabled
    2. Eager mode with `tf.function` decorations disabled
    3. Graph mode (eveything)

  When applied to a test class, all the methods in the class are affected.

  Args:
    test_class_or_method: the `TestCase` class or method to decorate.

  Returns:
    decorator: A generated TF `test_combinations` decorator, or if
    `test_class_or_method` is not `None`, the generated decorator applied to
    that function.
  """
  decorator = test_combinations.generate(
      (test_combinations.combine(mode='graph',
                                 tf_function='') +
       test_combinations.combine(
           mode='eager', tf_function=['', 'no_tf_function'])),
      test_combinations=[
          EagerGraphCombination(),
          ExecuteFunctionsEagerlyCombination(),
      ])

  if test_class_or_method:
    return decorator(test_class_or_method)
  return decorator


def test_graph_and_eager_modes(test_class_or_method=None):
  """Decorator for generating graph and eager mode tests from a single test.

  Must be applied to subclasses of `parameterized.TestCase` (from
  absl/testing), or a method of such a subclass.

  When applied to a test method, this decorator results in the replacement of
  that method with a two new test methods, one executed in graph mode and the
  other in eager mode.

  When applied to a test class, all the methods in the class are affected.

  Args:
    test_class_or_method: the `TestCase` class or method to decorate.

  Returns:
    decorator: A generated TF `test_combinations` decorator, or if
    `test_class_or_method` is not `None`, the generated decorator applied to
    that function.
  """
  decorator = test_combinations.generate(
      test_combinations.combine(mode=['graph', 'eager']),
      test_combinations=[EagerGraphCombination()])

  if test_class_or_method:
    return decorator(test_class_or_method)
  return decorator


JAX_MODE = False


def numpy_disable_gradient_test(test_fn):
  """Disable a gradient-using test when using the numpy backend."""

  if JAX_MODE:
    return test_fn

  def new_test(self, *args, **kwargs):
    if tf.Variable == ops.NumpyVariable:
      self.skipTest('gradient-using test disabled for numpy')
    return test_fn(self, *args, **kwargs)

  return new_test


def jax_disable_variable_test(test_fn):
  """Disable a Variable-using test when using the JAX backend."""

  if not JAX_MODE:
    return test_fn

  def new_test(self, *args, **kwargs):
    self.skipTest('tf.Variable-using test disabled for JAX')
    return test_fn(self, *args, **kwargs)

  return new_test


def numpy_disable_test_missing_functionality(issue_link):
  """Disable a test for unimplemented numpy functionality."""

  def f(test_fn):
    """Decorator."""
    if JAX_MODE:
      return test_fn

    def new_test(self, *args, **kwargs):
      if tf.Variable == ops.NumpyVariable:
        msg = 'Test disabled for numpy missing functionality: {}'
        self.skipTest(msg.format(issue_link))
      return test_fn(self, *args, **kwargs)

    return new_test

  return f


def jax_disable_test_missing_functionality(issue_link):
  """Disable a test for unimplemented JAX functionality."""

  def f(test_fn):
    if not JAX_MODE:
      return test_fn

    def new_test(self, *args, **kwargs):
      self.skipTest(
          'Test disabled for JAX missing functionality: {}'.format(issue_link))
      return test_fn(self, *args, **kwargs)

    return new_test

  return f


def test_seed(hardcoded_seed=None, set_eager_seed=True):
  """Returns a command-line-controllable PRNG seed for unit tests.

  If your test will pass a seed to more than one operation, consider using
  `test_seed_stream` instead.

  When seeding unit-test PRNGs, we want:

  - The seed to be fixed to an arbitrary value most of the time, so the test
    doesn't flake even if its failure probability is noticeable.

  - To switch to different seeds per run when using --runs_per_test to measure
    the test's failure probability.

  - To set the seed to a specific value when reproducing a low-probability event
    (e.g., debugging a crash that only some seeds trigger).

  To those ends, this function returns 17, but respects the command line flags
  `--fixed_seed=<seed>` and `--vary_seed` (Boolean, default False).
  `--vary_seed` uses system entropy to produce unpredictable seeds.
  `--fixed_seed` takes precedence over `--vary_seed` when both are present.

  Note that TensorFlow graph mode operations tend to read seed state from two
  sources: a "graph-level seed" and an "op-level seed".  test_util.TestCase will
  set the former to a fixed value per test, but in general it may be necessary
  to explicitly set both to ensure reproducibility.

  Args:
    hardcoded_seed: Optional Python value.  The seed to use instead of 17 if
      both the `--vary_seed` and `--fixed_seed` flags are unset.  This should
      usually be unnecessary, since a test should pass with any seed.
    set_eager_seed: Python bool.  If true (default), invoke `tf.set_random_seed`
      in Eager mode to get more reproducibility.  Should become unnecessary
      once b/68017812 is resolved.

  Returns:
    seed: 17, unless otherwise specified by arguments or command line flags.
  """
  if flags.FLAGS.fixed_seed is not None:
    answer = int(flags.FLAGS.fixed_seed)
  elif flags.FLAGS.vary_seed:
    entropy = os.urandom(64)
    # Why does Python make it so hard to just grab a bunch of bytes from
    # /dev/urandom and get them interpreted as an integer?  Oh, well.
    if six.PY2:
      answer = int(entropy.encode('hex'), 16)
    else:
      answer = int.from_bytes(entropy, 'big')
    logging.warning('Using seed %s', answer)
  elif hardcoded_seed is not None:
    answer = hardcoded_seed
  else:
    answer = 17
  return (_wrap_seed_jax if JAX_MODE else _wrap_seed)(answer, set_eager_seed)


def _wrap_seed(seed, set_eager_seed):
  # TODO(b/68017812): Remove this clause once eager correctly supports seeding.
  if tf.executing_eagerly() and set_eager_seed:
    tf1.set_random_seed(seed)
  return seed


def _wrap_seed_jax(seed, _):
  import jax.random as jaxrand  # pylint: disable=g-import-not-at-top
  return jaxrand.PRNGKey(seed % (2**32 - 1))


def test_seed_stream(salt='Salt of the Earth', hardcoded_seed=None):
  """Returns a command-line-controllable SeedStream PRNG for unit tests.

  When seeding unit-test PRNGs, we want:

  - The seed to be fixed to an arbitrary value most of the time, so the test
    doesn't flake even if its failure probability is noticeable.

  - To switch to different seeds per run when using --runs_per_test to measure
    the test's failure probability.

  - To set the seed to a specific value when reproducing a low-probability event
    (e.g., debugging a crash that only some seeds trigger).

  To those ends, this function returns a `SeedStream` seeded with `test_seed`
  (which see).  The latter respects the command line flags `--fixed_seed=<seed>`
  and `--vary-seed` (Boolean, default False).  `--vary_seed` uses system entropy
  to produce unpredictable seeds.  `--fixed_seed` takes precedence over
  `--vary_seed` when both are present.

  Note that TensorFlow graph mode operations tend to read seed state from two
  sources: a "graph-level seed" and an "op-level seed".  test_util.TestCase will
  set the former to a fixed value per test, but in general it may be necessary
  to explicitly set both to ensure reproducibility.

  Args:
    salt: Optional string wherewith to salt the returned SeedStream.  Setting
      this guarantees independent random numbers across tests.
    hardcoded_seed: Optional Python value.  The seed to use if both the
      `--vary_seed` and `--fixed_seed` flags are unset.  This should usually be
      unnecessary, since a test should pass with any seed.

  Returns:
    strm: A SeedStream instance seeded with 17, unless otherwise specified by
      arguments or command line flags.
  """
  return SeedStream(test_seed(hardcoded_seed), salt=salt)


class DiscreteScalarDistributionTestHelpers(object):
  """DiscreteScalarDistributionTestHelpers."""

  def run_test_sample_consistent_log_prob(
      self, sess_run_fn, dist,
      num_samples=int(1e5), num_threshold=int(1e3), seed=None,
      batch_size=None,
      rtol=1e-2, atol=0.):
    """Tests that sample/log_prob are consistent with each other.

    "Consistency" means that `sample` and `log_prob` correspond to the same
    distribution.

    Note: this test only verifies a necessary condition for consistency--it does
    does not verify sufficiency hence does not prove `sample`, `log_prob` truly
    are consistent.

    Args:
      sess_run_fn: Python `callable` taking `list`-like of `Tensor`s and
        returning a list of results after running one "step" of TensorFlow
        computation, typically set to `sess.run`.
      dist: Distribution instance or object which implements `sample`,
        `log_prob`, `event_shape_tensor` and `batch_shape_tensor`.
      num_samples: Python `int` scalar indicating the number of Monte-Carlo
        samples to draw from `dist`.
      num_threshold: Python `int` scalar indicating the number of samples a
        bucket must contain before being compared to the probability.
        Default value: 1e3; must be at least 1.
        Warning, set too high will cause test to falsely pass but setting too
        low will cause the test to falsely fail.
      seed: Python `int` indicating the seed to use when sampling from `dist`.
        In general it is not recommended to use `None` during a test as this
        increases the likelihood of spurious test failure.
      batch_size: Hint for unpacking result of samples. Default: `None` means
        batch_size is inferred.
      rtol: Python `float`-type indicating the admissible relative error between
        analytical and sample statistics.
      atol: Python `float`-type indicating the admissible absolute error between
        analytical and sample statistics.

    Raises:
      ValueError: if `num_threshold < 1`.
    """
    if num_threshold < 1:
      raise ValueError('num_threshold({}) must be at least 1.'.format(
          num_threshold))
    # Histogram only supports vectors so we call it once per batch coordinate.
    y = dist.sample(num_samples, seed=test_seed_stream(hardcoded_seed=seed))
    y = tf.reshape(y, shape=[num_samples, -1])
    if batch_size is None:
      batch_size = tf.reduce_prod(input_tensor=dist.batch_shape_tensor())
    batch_dims = tf.shape(input=dist.batch_shape_tensor())[0]
    edges_expanded_shape = 1 + tf.pad(tensor=[-2], paddings=[[0, batch_dims]])
    for b, x in enumerate(tf.unstack(y, num=batch_size, axis=1)):
      counts, edges = self.histogram(x)
      edges = tf.reshape(edges, edges_expanded_shape)
      probs = tf.exp(dist.log_prob(edges))
      probs = tf.reshape(probs, shape=[-1, batch_size])[:, b]

      [counts_, probs_] = sess_run_fn([counts, probs])
      valid = counts_ > num_threshold
      probs_ = probs_[valid]
      counts_ = counts_[valid]
      self.assertAllClose(probs_, counts_ / num_samples,
                          rtol=rtol, atol=atol)

  def run_test_sample_consistent_mean_variance(
      self, sess_run_fn, dist,
      num_samples=int(1e5), seed=None,
      rtol=1e-2, atol=0.):
    """Tests that sample/mean/variance are consistent with each other.

    "Consistency" means that `sample`, `mean`, `variance`, etc all correspond
    to the same distribution.

    Args:
      sess_run_fn: Python `callable` taking `list`-like of `Tensor`s and
        returning a list of results after running one "step" of TensorFlow
        computation, typically set to `sess.run`.
      dist: Distribution instance or object which implements `sample`,
        `log_prob`, `event_shape_tensor` and `batch_shape_tensor`.
      num_samples: Python `int` scalar indicating the number of Monte-Carlo
        samples to draw from `dist`.
      seed: Python `int` indicating the seed to use when sampling from `dist`.
        In general it is not recommended to use `None` during a test as this
        increases the likelihood of spurious test failure.
      rtol: Python `float`-type indicating the admissible relative error between
        analytical and sample statistics.
      atol: Python `float`-type indicating the admissible absolute error between
        analytical and sample statistics.
    """
    x = tf.cast(dist.sample(num_samples,
                            seed=test_seed_stream(hardcoded_seed=seed)),
                dtype=tf.float32)
    sample_mean = tf.reduce_mean(input_tensor=x, axis=0)
    sample_variance = tf.reduce_mean(
        input_tensor=tf.square(x - sample_mean), axis=0)
    sample_stddev = tf.sqrt(sample_variance)

    [
        sample_mean_,
        sample_variance_,
        sample_stddev_,
        mean_,
        variance_,
        stddev_
    ] = sess_run_fn([
        sample_mean,
        sample_variance,
        sample_stddev,
        dist.mean(),
        dist.variance(),
        dist.stddev(),
    ])

    self.assertAllClose(mean_, sample_mean_, rtol=rtol, atol=atol)
    self.assertAllClose(variance_, sample_variance_, rtol=rtol, atol=atol)
    self.assertAllClose(stddev_, sample_stddev_, rtol=rtol, atol=atol)

  def histogram(self, x, value_range=None, nbins=None, name=None):
    """Return histogram of values.

    Given the tensor `values`, this operation returns a rank 1 histogram
    counting the number of entries in `values` that fell into every bin. The
    bins are equal width and determined by the arguments `value_range` and
    `nbins`.

    Args:
      x: 1D numeric `Tensor` of items to count.
      value_range:  Shape [2] `Tensor`. `new_values <= value_range[0]` will be
        mapped to `hist[0]`, `values >= value_range[1]` will be mapped to
        `hist[-1]`. Must be same dtype as `x`.
      nbins:  Scalar `int32 Tensor`.  Number of histogram bins.
      name: Python `str` name prefixed to Ops created by this class.

    Returns:
      counts: 1D `Tensor` of counts, i.e.,
        `counts[i] = sum{ edges[i-1] <= values[j] < edges[i] : j }`.
      edges: 1D `Tensor` characterizing intervals used for counting.
    """
    with tf.name_scope(name or 'histogram'):
      x = tf.convert_to_tensor(value=x, name='x')
      if value_range is None:
        value_range = [
            tf.reduce_min(input_tensor=x), 1 + tf.reduce_max(input_tensor=x)
        ]
      value_range = tf.convert_to_tensor(value=value_range, name='value_range')
      lo = value_range[0]
      hi = value_range[1]
      if nbins is None:
        nbins = tf.cast(hi - lo, dtype=tf.int32)
      delta = (hi - lo) / tf.cast(
          nbins, dtype=dtype_util.base_dtype(value_range.dtype))
      edges = tf.range(
          start=lo, limit=hi, delta=delta, dtype=dtype_util.base_dtype(x.dtype))
      counts = tf.histogram_fixed_width(x, value_range=value_range, nbins=nbins)
      return counts, edges


class VectorDistributionTestHelpers(object):
  """VectorDistributionTestHelpers helps test vector-event distributions."""

  def run_test_sample_consistent_log_prob(
      self,
      sess_run_fn,
      dist,
      num_samples=int(1e5),
      radius=1.,
      center=0.,
      seed=None,
      rtol=1e-2,
      atol=0.):
    """Tests that sample/log_prob are mutually consistent.

    "Consistency" means that `sample` and `log_prob` correspond to the same
    distribution.

    The idea of this test is to compute the Monte-Carlo estimate of the volume
    enclosed by a hypersphere, i.e., the volume of an `n`-ball. While we could
    choose an arbitrary function to integrate, the hypersphere's volume is nice
    because it is intuitive, has an easy analytical expression, and works for
    `dimensions > 1`.

    Technical Details:

    Observe that:

    ```none
    int_{R**d} dx [x in Ball(radius=r, center=c)]
    = E_{p(X)}[ [X in Ball(r, c)] / p(X) ]
    = lim_{m->infty} m**-1 sum_j^m [x[j] in Ball(r, c)] / p(x[j]),
        where x[j] ~iid p(X)
    ```

    Thus, for fixed `m`, the above is approximately true when `sample` and
    `log_prob` are mutually consistent.

    Furthermore, the above calculation has the analytical result:
    `pi**(d/2) r**d / Gamma(1 + d/2)`.

    Note: this test only verifies a necessary condition for consistency--it does
    does not verify sufficiency hence does not prove `sample`, `log_prob` truly
    are consistent. For this reason we recommend testing several different
    hyperspheres (assuming the hypersphere is supported by the distribution).
    Furthermore, we gain additional trust in this test when also tested `sample`
    against the first, second moments
    (`run_test_sample_consistent_mean_covariance`); it is probably unlikely that
    a "best-effort" implementation of `log_prob` would incorrectly pass both
    tests and for different hyperspheres.

    For a discussion on the analytical result (second-line) see:
      https://en.wikipedia.org/wiki/Volume_of_an_n-ball.

    For a discussion of importance sampling (fourth-line) see:
      https://en.wikipedia.org/wiki/Importance_sampling.

    Args:
      sess_run_fn: Python `callable` taking `list`-like of `Tensor`s and
        returning a list of results after running one "step" of TensorFlow
        computation, typically set to `sess.run`.
      dist: Distribution instance or object which implements `sample`,
        `log_prob`, `event_shape_tensor` and `batch_shape_tensor`. The
        distribution must have non-zero probability of sampling every point
        enclosed by the hypersphere.
      num_samples: Python `int` scalar indicating the number of Monte-Carlo
        samples to draw from `dist`.
      radius: Python `float`-type indicating the radius of the `n`-ball which
        we're computing the volume.
      center: Python floating-type vector (or scalar) indicating the center of
        the `n`-ball which we're computing the volume. When scalar, the value is
        broadcast to all event dims.
      seed: Python `int` indicating the seed to use when sampling from `dist`.
        In general it is not recommended to use `None` during a test as this
        increases the likelihood of spurious test failure.
      rtol: Python `float`-type indicating the admissible relative error between
        actual- and approximate-volumes.
      atol: Python `float`-type indicating the admissible absolute error between
        actual- and approximate-volumes. In general this should be zero since
        a typical radius implies a non-zero volume.
    """

    def actual_hypersphere_volume(dims, radius):
      # https://en.wikipedia.org/wiki/Volume_of_an_n-ball
      # Using tf.lgamma because we'd have to otherwise use SciPy which is not
      # a required dependency of core.
      radius = np.asarray(radius)
      dims = tf.cast(dims, dtype=radius.dtype)
      return tf.exp((dims / 2.) * np.log(np.pi) -
                    tf.math.lgamma(1. + dims / 2.) + dims * tf.math.log(radius))

    def monte_carlo_hypersphere_volume(dist, num_samples, radius, center):
      # https://en.wikipedia.org/wiki/Importance_sampling
      x = dist.sample(num_samples, seed=test_seed_stream(hardcoded_seed=seed))
      x = tf.identity(x)  # Invalidate bijector cacheing.
      inverse_log_prob = tf.exp(-dist.log_prob(x))
      importance_weights = tf1.where(
          tf.norm(tensor=x - center, axis=-1) <= radius, inverse_log_prob,
          tf.zeros_like(inverse_log_prob))
      return tf.reduce_mean(input_tensor=importance_weights, axis=0)

    # Build graph.
    with tf.name_scope('run_test_sample_consistent_log_prob'):
      batch_shape = dist.batch_shape_tensor()
      actual_volume = actual_hypersphere_volume(
          dims=dist.event_shape_tensor()[0],
          radius=radius)
      sample_volume = monte_carlo_hypersphere_volume(
          dist,
          num_samples=num_samples,
          radius=radius,
          center=center)
      init_op = tf1.global_variables_initializer()

    # Execute graph.
    sess_run_fn(init_op)
    [batch_shape_, actual_volume_, sample_volume_] = sess_run_fn([
        batch_shape, actual_volume, sample_volume])

    # Check results.
    self.assertAllClose(np.tile(actual_volume_, reps=batch_shape_),
                        sample_volume_,
                        rtol=rtol, atol=atol)

  def run_test_sample_consistent_mean_covariance(
      self,
      sess_run_fn,
      dist,
      num_samples=int(1e5),
      seed=None,
      rtol=1e-2,
      atol=0.1,
      cov_rtol=None,
      cov_atol=None):
    """Tests that sample/mean/covariance are consistent with each other.

    "Consistency" means that `sample`, `mean`, `covariance`, etc all correspond
    to the same distribution.

    Args:
      sess_run_fn: Python `callable` taking `list`-like of `Tensor`s and
        returning a list of results after running one "step" of TensorFlow
        computation, typically set to `sess.run`.
      dist: Distribution instance or object which implements `sample`,
        `log_prob`, `event_shape_tensor` and `batch_shape_tensor`.
      num_samples: Python `int` scalar indicating the number of Monte-Carlo
        samples to draw from `dist`.
      seed: Python `int` indicating the seed to use when sampling from `dist`.
        In general it is not recommended to use `None` during a test as this
        increases the likelihood of spurious test failure.
      rtol: Python `float`-type indicating the admissible relative error between
        analytical and sample statistics.
      atol: Python `float`-type indicating the admissible absolute error between
        analytical and sample statistics.
      cov_rtol: Python `float`-type indicating the admissible relative error
        between analytical and sample covariance. Default: rtol.
      cov_atol: Python `float`-type indicating the admissible absolute error
        between analytical and sample covariance. Default: atol.
    """

    x = dist.sample(num_samples, seed=test_seed_stream(hardcoded_seed=seed))
    sample_mean = tf.reduce_mean(input_tensor=x, axis=0)
    sample_covariance = tf.reduce_mean(
        input_tensor=_vec_outer_square(x - sample_mean), axis=0)
    sample_variance = tf.linalg.diag_part(sample_covariance)
    sample_stddev = tf.sqrt(sample_variance)

    [
        sample_mean_,
        sample_covariance_,
        sample_variance_,
        sample_stddev_,
        mean_,
        covariance_,
        variance_,
        stddev_
    ] = sess_run_fn([
        sample_mean,
        sample_covariance,
        sample_variance,
        sample_stddev,
        dist.mean(),
        dist.covariance(),
        dist.variance(),
        dist.stddev(),
    ])

    self.assertAllClose(mean_, sample_mean_, rtol=rtol, atol=atol)
    self.assertAllClose(covariance_, sample_covariance_,
                        rtol=cov_rtol or rtol,
                        atol=cov_atol or atol)
    self.assertAllClose(variance_, sample_variance_, rtol=rtol, atol=atol)
    self.assertAllClose(stddev_, sample_stddev_, rtol=rtol, atol=atol)


def _vec_outer_square(x, name=None):
  """Computes the outer-product of a vector, i.e., x.T x."""
  with tf.name_scope(name or 'vec_osquare'):
    return x[..., :, tf.newaxis] * x[..., tf.newaxis, :]
