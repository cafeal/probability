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
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


# Dependency imports
import numpy as np
from scipy import special as sp_special
from scipy import stats as sp_stats

import tensorflow.compat.v2 as tf
import tensorflow_probability as tfp

from tensorflow_probability.python.internal import test_util

tfd = tfp.distributions


@test_util.test_all_tf_execution_regimes
class GammaTest(test_util.TestCase):

  def testGammaShape(self):
    alpha = tf.constant([3.0] * 5)
    beta = tf.constant(11.0)
    gamma = tfd.Gamma(concentration=alpha, rate=beta, validate_args=True)

    self.assertEqual(self.evaluate(gamma.batch_shape_tensor()), (5,))
    self.assertEqual(gamma.batch_shape, tf.TensorShape([5]))
    self.assertAllEqual(self.evaluate(gamma.event_shape_tensor()), [])
    self.assertEqual(gamma.event_shape, tf.TensorShape([]))

  def testGammaLogPDF(self):
    batch_size = 6
    alpha = tf.constant([2.0] * batch_size)
    beta = tf.constant([3.0] * batch_size)
    alpha_v = 2.0
    beta_v = 3.0
    x = np.array([2.5, 2.5, 4.0, 0.1, 1.0, 2.0], dtype=np.float32)
    gamma = tfd.Gamma(concentration=alpha, rate=beta, validate_args=True)
    log_pdf = gamma.log_prob(x)
    self.assertEqual(log_pdf.shape, (6,))
    pdf = gamma.prob(x)
    self.assertEqual(pdf.shape, (6,))
    expected_log_pdf = sp_stats.gamma.logpdf(x, alpha_v, scale=1 / beta_v)
    self.assertAllClose(self.evaluate(log_pdf), expected_log_pdf)
    self.assertAllClose(self.evaluate(pdf), np.exp(expected_log_pdf))

  def testGammaLogPDFBoundary(self):
    # When concentration = 1, we have an exponential distribution. Check that at
    # 0 we have finite log prob.
    rate = np.array([0.1, 0.5, 1., 2., 5., 10.], dtype=np.float32)
    gamma = tfd.Gamma(concentration=1., rate=rate, validate_args=True)
    log_pdf = gamma.log_prob(0.)
    self.assertAllClose(np.log(rate), self.evaluate(log_pdf))

    gamma = tfd.Gamma(concentration=[2., 4., 0.5], rate=6., validate_args=True)
    log_pdf = self.evaluate(gamma.log_prob(0.))
    self.assertAllNegativeInf(log_pdf[:2])
    self.assertAllPositiveInf(log_pdf[2])

    pdf = self.evaluate(gamma.prob(0.))
    self.assertAllPositiveInf(pdf[2])
    self.assertAllFinite(pdf[:2])

  def testAssertsValidSample(self):
    g = tfd.Gamma(concentration=2., rate=3., validate_args=True)
    with self.assertRaisesOpError('Sample must be non-negative.'):
      self.evaluate(g.log_prob(-.1))

  def testGammaLogPDFMultidimensional(self):
    batch_size = 6
    alpha = tf.constant([[2.0, 4.0]] * batch_size)
    beta = tf.constant([[3.0, 4.0]] * batch_size)
    alpha_v = np.array([2.0, 4.0])
    beta_v = np.array([3.0, 4.0])
    x = np.array([[2.5, 2.5, 4.0, 0.1, 1.0, 2.0]], dtype=np.float32).T
    gamma = tfd.Gamma(concentration=alpha, rate=beta, validate_args=True)
    log_pdf = gamma.log_prob(x)
    log_pdf_values = self.evaluate(log_pdf)
    self.assertEqual(log_pdf.shape, (6, 2))
    pdf = gamma.prob(x)
    pdf_values = self.evaluate(pdf)
    self.assertEqual(pdf.shape, (6, 2))
    expected_log_pdf = sp_stats.gamma.logpdf(x, alpha_v, scale=1 / beta_v)
    self.assertAllClose(log_pdf_values, expected_log_pdf)
    self.assertAllClose(pdf_values, np.exp(expected_log_pdf))

  def testGammaLogPDFMultidimensionalBroadcasting(self):
    batch_size = 6
    alpha = tf.constant([[2.0, 4.0]] * batch_size)
    beta = tf.constant(3.0)
    alpha_v = np.array([2.0, 4.0])
    beta_v = 3.0
    x = np.array([[2.5, 2.5, 4.0, 0.1, 1.0, 2.0]], dtype=np.float32).T
    gamma = tfd.Gamma(concentration=alpha, rate=beta, validate_args=True)
    log_pdf = gamma.log_prob(x)
    log_pdf_values = self.evaluate(log_pdf)
    self.assertEqual(log_pdf.shape, (6, 2))
    pdf = gamma.prob(x)
    pdf_values = self.evaluate(pdf)
    self.assertEqual(pdf.shape, (6, 2))

    expected_log_pdf = sp_stats.gamma.logpdf(x, alpha_v, scale=1 / beta_v)
    self.assertAllClose(log_pdf_values, expected_log_pdf)
    self.assertAllClose(pdf_values, np.exp(expected_log_pdf))

  def testGammaCDF(self):
    batch_size = 6
    alpha = tf.constant([2.0] * batch_size)
    beta = tf.constant([3.0] * batch_size)
    alpha_v = 2.0
    beta_v = 3.0
    x = np.array([2.5, 2.5, 4.0, 0.1, 1.0, 2.0], dtype=np.float32)

    gamma = tfd.Gamma(concentration=alpha, rate=beta, validate_args=True)
    cdf = gamma.cdf(x)
    self.assertEqual(cdf.shape, (6,))
    expected_cdf = sp_stats.gamma.cdf(x, alpha_v, scale=1 / beta_v)
    self.assertAllClose(self.evaluate(cdf), expected_cdf)

  def testGammaMean(self):
    alpha_v = np.array([1.0, 3.0, 2.5])
    beta_v = np.array([1.0, 4.0, 5.0])
    gamma = tfd.Gamma(concentration=alpha_v, rate=beta_v, validate_args=True)
    self.assertEqual(gamma.mean().shape, (3,))
    expected_means = sp_stats.gamma.mean(alpha_v, scale=1 / beta_v)
    self.assertAllClose(self.evaluate(gamma.mean()), expected_means)

  def testGammaModeAllowNanStatsIsFalseWorksWhenAllBatchMembersAreDefined(self):
    alpha_v = np.array([5.5, 3.0, 2.5])
    beta_v = np.array([1.0, 4.0, 5.0])
    gamma = tfd.Gamma(concentration=alpha_v, rate=beta_v, validate_args=True)
    expected_modes = (alpha_v - 1) / beta_v
    self.assertEqual(gamma.mode().shape, (3,))
    self.assertAllClose(self.evaluate(gamma.mode()), expected_modes)

  def testGammaModeAllowNanStatsFalseRaisesForUndefinedBatchMembers(self):
    # Mode will not be defined for the first entry.
    alpha_v = np.array([0.5, 3.0, 2.5])
    beta_v = np.array([1.0, 4.0, 5.0])
    gamma = tfd.Gamma(
        concentration=alpha_v,
        rate=beta_v,
        allow_nan_stats=False,
        validate_args=True)
    with self.assertRaisesOpError(
        'Mode not defined when any concentration <= 1.'):
      self.evaluate(gamma.mode())

  def testGammaModeAllowNanStatsIsTrueReturnsNaNforUndefinedBatchMembers(self):
    # Mode will not be defined for the first entry.
    alpha_v = np.array([0.5, 3.0, 2.5])
    beta_v = np.array([1.0, 4.0, 5.0])
    gamma = tfd.Gamma(
        concentration=alpha_v,
        rate=beta_v,
        allow_nan_stats=True,
        validate_args=True)
    expected_modes = (alpha_v - 1) / beta_v
    expected_modes[0] = np.nan
    self.assertEqual(gamma.mode().shape, (3,))
    self.assertAllClose(self.evaluate(gamma.mode()), expected_modes)

  def testGammaVariance(self):
    alpha_v = np.array([1.0, 3.0, 2.5])
    beta_v = np.array([1.0, 4.0, 5.0])
    gamma = tfd.Gamma(concentration=alpha_v, rate=beta_v, validate_args=True)
    self.assertEqual(gamma.variance().shape, (3,))
    expected_variances = sp_stats.gamma.var(alpha_v, scale=1 / beta_v)
    self.assertAllClose(self.evaluate(gamma.variance()), expected_variances)

  def testGammaStd(self):
    alpha_v = np.array([1.0, 3.0, 2.5])
    beta_v = np.array([1.0, 4.0, 5.0])
    gamma = tfd.Gamma(concentration=alpha_v, rate=beta_v, validate_args=True)
    self.assertEqual(gamma.stddev().shape, (3,))
    expected_stddev = sp_stats.gamma.std(alpha_v, scale=1. / beta_v)
    self.assertAllClose(self.evaluate(gamma.stddev()), expected_stddev)

  def testGammaEntropy(self):
    alpha_v = np.array([1.0, 3.0, 2.5])
    beta_v = np.array([1.0, 4.0, 5.0])
    gamma = tfd.Gamma(concentration=alpha_v, rate=beta_v, validate_args=True)
    self.assertEqual(gamma.entropy().shape, (3,))
    expected_entropy = sp_stats.gamma.entropy(alpha_v, scale=1 / beta_v)
    self.assertAllClose(self.evaluate(gamma.entropy()), expected_entropy)

  def testGammaSampleSmallAlpha(self):
    alpha_v = 0.05
    beta_v = 1.0
    alpha = tf.constant(alpha_v)
    beta = tf.constant(beta_v)
    n = 100000
    gamma = tfd.Gamma(concentration=alpha, rate=beta, validate_args=True)
    samples = gamma.sample(n, seed=test_util.test_seed())
    sample_values = self.evaluate(samples)
    self.assertEqual(samples.shape, (n,))
    self.assertEqual(sample_values.shape, (n,))
    self.assertTrue(self._kstest(alpha_v, beta_v, sample_values))
    self.assertAllClose(
        sample_values.mean(),
        sp_stats.gamma.mean(alpha_v, scale=1 / beta_v),
        atol=.01)
    self.assertAllClose(
        sample_values.var(),
        sp_stats.gamma.var(alpha_v, scale=1 / beta_v),
        atol=.15)

  def testGammaSample(self):
    alpha_v = 4.0
    beta_v = 3.0
    alpha = tf.constant(alpha_v)
    beta = tf.constant(beta_v)
    n = 100000
    gamma = tfd.Gamma(concentration=alpha, rate=beta, validate_args=True)
    samples = gamma.sample(n, seed=test_util.test_seed())
    sample_values = self.evaluate(samples)
    self.assertEqual(samples.shape, (n,))
    self.assertEqual(sample_values.shape, (n,))
    self.assertTrue(self._kstest(alpha_v, beta_v, sample_values))
    self.assertAllClose(
        sample_values.mean(),
        sp_stats.gamma.mean(alpha_v, scale=1 / beta_v),
        atol=.01)
    self.assertAllClose(
        sample_values.var(),
        sp_stats.gamma.var(alpha_v, scale=1 / beta_v),
        atol=.15)

  @test_util.numpy_disable_gradient_test
  def testGammaFullyReparameterized(self):
    alpha = tf.constant(4.0)
    beta = tf.constant(3.0)
    _, [grad_alpha, grad_beta] = tfp.math.value_and_gradient(
        lambda a, b: tfd.Gamma(concentration=a, rate=b, validate_args=True).  # pylint: disable=g-long-lambda
        sample(100, seed=test_util.test_seed()), [alpha, beta])
    self.assertIsNotNone(grad_alpha)
    self.assertIsNotNone(grad_beta)

  def testGammaSampleMultiDimensional(self):
    alpha_v = np.array([np.arange(1, 101, dtype=np.float32)])  # 1 x 100
    beta_v = np.array([np.arange(1, 11, dtype=np.float32)]).T  # 10 x 1
    gamma = tfd.Gamma(concentration=alpha_v, rate=beta_v, validate_args=True)
    n = 10000
    samples = gamma.sample(n, seed=test_util.test_seed())
    sample_values = self.evaluate(samples)
    self.assertEqual(samples.shape, (n, 10, 100))
    self.assertEqual(sample_values.shape, (n, 10, 100))
    zeros = np.zeros_like(alpha_v + beta_v)  # 10 x 100
    alpha_bc = alpha_v + zeros
    beta_bc = beta_v + zeros
    self.assertAllClose(
        sample_values.mean(axis=0),
        sp_stats.gamma.mean(alpha_bc, scale=1 / beta_bc),
        atol=0.,
        rtol=.05)
    self.assertAllClose(
        sample_values.var(axis=0),
        sp_stats.gamma.var(alpha_bc, scale=1 / beta_bc),
        atol=10.0,
        rtol=0.)
    fails = 0
    trials = 0
    for ai, a in enumerate(np.reshape(alpha_v, [-1])):
      for bi, b in enumerate(np.reshape(beta_v, [-1])):
        s = sample_values[:, bi, ai]
        trials += 1
        fails += 0 if self._kstest(a, b, s) else 1
    self.assertLess(fails, trials * 0.03)

  def _kstest(self, alpha, beta, samples):
    # Uses the Kolmogorov-Smirnov test for goodness of fit.
    ks, _ = sp_stats.kstest(samples, sp_stats.gamma(alpha, scale=1 / beta).cdf)
    # Return True when the test passes.
    return ks < 0.02

  def testGammaPdfOfSampleMultiDims(self):
    gamma = tfd.Gamma(
        concentration=[7., 11.], rate=[[5.], [6.]], validate_args=True)
    num = 50000
    samples = gamma.sample(num, seed=test_util.test_seed())
    pdfs = gamma.prob(samples)
    sample_vals, pdf_vals = self.evaluate([samples, pdfs])
    self.assertEqual(samples.shape, (num, 2, 2))
    self.assertEqual(pdfs.shape, (num, 2, 2))
    self._assertIntegral(sample_vals[:, 0, 0], pdf_vals[:, 0, 0], err=0.02)
    self._assertIntegral(sample_vals[:, 0, 1], pdf_vals[:, 0, 1], err=0.02)
    self._assertIntegral(sample_vals[:, 1, 0], pdf_vals[:, 1, 0], err=0.02)
    self._assertIntegral(sample_vals[:, 1, 1], pdf_vals[:, 1, 1], err=0.02)
    self.assertAllClose(
        sp_stats.gamma.mean([[7., 11.], [7., 11.]],
                            scale=1 / np.array([[5., 5.], [6., 6.]])),
        sample_vals.mean(axis=0),
        atol=.1)
    self.assertAllClose(
        sp_stats.gamma.var([[7., 11.], [7., 11.]],
                           scale=1 / np.array([[5., 5.], [6., 6.]])),
        sample_vals.var(axis=0),
        atol=.1)

  def _assertIntegral(self, sample_vals, pdf_vals, err=1e-3):
    s_p = zip(sample_vals, pdf_vals)
    prev = (0, 0)
    total = 0
    for k in sorted(s_p, key=lambda x: x[0]):
      pair_pdf = (k[1] + prev[1]) / 2
      total += (k[0] - prev[0]) * pair_pdf
      prev = k
    self.assertNear(1., total, err=err)

  def testGammaNonPositiveInitializationParamsRaises(self):
    alpha_v = tf.constant(0.0, name='alpha')
    beta_v = tf.constant(1.0, name='beta')
    with self.assertRaisesOpError('Argument `concentration` must be positive.'):
      gamma = tfd.Gamma(
          concentration=alpha_v, rate=beta_v, validate_args=True)
      self.evaluate(gamma.mean())
    alpha_v = tf.constant(1.0, name='alpha')
    beta_v = tf.constant(0.0, name='beta')
    with self.assertRaisesOpError('Argument `rate` must be positive.'):
      gamma = tfd.Gamma(
          concentration=alpha_v, rate=beta_v, validate_args=True)
      self.evaluate(gamma.mean())

  def testGammaGammaKL(self):
    alpha0 = np.array([3.])
    beta0 = np.array([1., 2., 3., 1.5, 2.5, 3.5])

    alpha1 = np.array([0.4])
    beta1 = np.array([0.5, 1., 1.5, 2., 2.5, 3.])

    # Build graph.
    g0 = tfd.Gamma(concentration=alpha0, rate=beta0, validate_args=True)
    g1 = tfd.Gamma(concentration=alpha1, rate=beta1, validate_args=True)
    x = g0.sample(int(1e4), seed=test_util.test_seed())
    kl_sample = tf.reduce_mean(g0.log_prob(x) - g1.log_prob(x), axis=0)
    kl_actual = tfd.kl_divergence(g0, g1)

    # Execute graph.
    [kl_sample_, kl_actual_] = self.evaluate([kl_sample, kl_actual])

    self.assertEqual(beta0.shape, kl_actual.shape)

    kl_expected = ((alpha0 - alpha1) * sp_special.digamma(alpha0)
                   + sp_special.gammaln(alpha1)
                   - sp_special.gammaln(alpha0)
                   + alpha1 * np.log(beta0)
                   - alpha1 * np.log(beta1)
                   + alpha0 * (beta1 / beta0 - 1.))

    self.assertAllClose(kl_expected, kl_actual_, atol=0., rtol=1e-6)
    self.assertAllClose(kl_sample_, kl_actual_, atol=0., rtol=1e-1)

  @test_util.numpy_disable_gradient_test
  @test_util.jax_disable_variable_test
  def testGradientThroughConcentration(self):
    concentration = tf.Variable(3.)
    d = tfd.Gamma(concentration=concentration, rate=5., validate_args=True)
    with tf.GradientTape() as tape:
      loss = -d.log_prob([1., 2., 4.])
    grad = tape.gradient(loss, d.trainable_variables)
    self.assertLen(grad, 1)
    self.assertAllNotNone(grad)

  @test_util.jax_disable_variable_test
  def testAssertsPositiveConcentration(self):
    concentration = tf.Variable([1., 2., -3.])
    self.evaluate(concentration.initializer)
    with self.assertRaisesOpError('Argument `concentration` must be positive.'):
      d = tfd.Gamma(concentration=concentration, rate=[5.], validate_args=True)
      self.evaluate(d.sample(seed=test_util.test_seed()))

  def testAssertsPositiveConcentrationAfterMutation(self):
    concentration = tf.Variable([1., 2., 3.])
    self.evaluate(concentration.initializer)
    d = tfd.Gamma(concentration=concentration, rate=[5.], validate_args=True)
    with self.assertRaisesOpError('Argument `concentration` must be positive.'):
      with tf.control_dependencies([concentration.assign([1., 2., -3.])]):
        self.evaluate(d.sample(seed=test_util.test_seed()))

  def testGradientThroughRate(self):
    rate = tf.Variable(3.)
    d = tfd.Gamma(concentration=1., rate=rate, validate_args=True)
    with tf.GradientTape() as tape:
      loss = -d.log_prob([1., 2., 4.])
    grad = tape.gradient(loss, d.trainable_variables)
    self.assertLen(grad, 1)
    self.assertAllNotNone(grad)

  def testAssertsPositiveRate(self):
    rate = tf.Variable([1., 2., -3.])
    self.evaluate(rate.initializer)
    with self.assertRaisesOpError('Argument `rate` must be positive.'):
      d = tfd.Gamma(concentration=[5.], rate=rate, validate_args=True)
      self.evaluate(d.sample(seed=test_util.test_seed()))

  def testAssertsPositiveRateAfterMutation(self):
    rate = tf.Variable([1., 2., 3.])
    self.evaluate(rate.initializer)
    d = tfd.Gamma(concentration=[3.], rate=rate, validate_args=True)
    self.evaluate(d.mean())
    with self.assertRaisesOpError('Argument `rate` must be positive.'):
      with tf.control_dependencies([rate.assign([1., 2., -3.])]):
        self.evaluate(d.sample(seed=test_util.test_seed()))

if __name__ == '__main__':
  tf.test.main()
