# Copyright 2019 The TensorFlow Probability Authors.
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
# Bijectors with the numpy backend.

# [internal] load python3.bzl

licenses(["notice"])  # Apache 2.0

package(
    default_visibility = [
        "//tensorflow_probability:__subpackages__",
    ],
)

exports_files(["LICENSE"])

FILENAMES = [
    "absolute_value",
    "affine_linear_operator",
    "affine",
    "affine_scalar",
    "batch_normalization",
    "bijector",
    "blockwise",
    "categorical_to_discrete",
    "chain",
    "cholesky_outer_product",
    "cholesky_to_inv_cholesky",
    "correlation_cholesky",
    "cumsum",
    "discrete_cosine_transform",
    "expm1",
    "exp",
    "ffjord",
    "fill_scale_tril",
    "fill_triangular",
    "gumbel_cdf",
    "identity",
    "inline",
    "invert",
    "iterated_sigmoid_centered",
    "kumaraswamy_cdf",
    # "masked_autoregressive",
    "matrix_inverse_tril",
    # "scale_matvec_lu",
    "normal_cdf",
    "ordered",
    "pad",
    "permute",
    "power_transform",
    # "real_nvp",
    "rational_quadratic_spline",
    "reciprocal",
    "reshape",
    "scale",
    "scale_matvec_diag",
    "scale_matvec_linear_operator",
    "scale_matvec_tril",
    "shift",
    "sigmoid",
    "sinh_arcsinh",
    "softfloor",
    "softmax_centered",
    "softplus",
    "softsign",
    "square",
    "tanh",
    "transform_diagonal",
    "transpose",
    "weibull_cdf",
]

TEST_FILENAMES = [filename + "_test" for filename in FILENAMES]

TAP_BLACKLIST = ["{}_test".format(f) for f in (
    "affine",
    "batch_normalization",
    "bijector",
    "categorical_to_discrete",
    "correlation_cholesky",
    "discrete_cosine_transform",
    "ffjord",
    "permute",
    "rational_quadratic_spline",
    "scale",
    "scale_matvec_diag",
    "scale_matvec_linear_operator",
    "scale_matvec_tril",
    "shift",
)]

[genrule(
    name = "rewrite_{}".format(filename),
    srcs = ["//tensorflow_probability/python/bijectors:{}.py".format(filename)],
    outs = ["{}.py".format(filename)],
    cmd = "$(location //tensorflow_probability/python/experimental/substrates/meta:rewrite) $(SRCS) > $@",
    tools = ["//tensorflow_probability/python/experimental/substrates/meta:rewrite"],
) for filename in [
    "__init__",
    "bijector_test_util",
    "hypothesis_testlib",
] + FILENAMES + TEST_FILENAMES]

DEPS = {
    "correlation_cholesky_test": [
        "//tensorflow_probability/python/experimental/substrates/numpy/distributions:lkj",
    ],
    # Most bijectors tests import only what they use; these are exceptions.
    "hypothesis_testlib": ["//tensorflow_probability"],
    "invert_test": ["//tensorflow_probability/python/experimental/substrates/numpy"],
    "ordered_test": ["//tensorflow_probability"],
    "transpose_test": ["//tensorflow_probability/python/experimental/substrates/numpy"],
}

[py_library(
    name = filename,
    srcs = ["{}.py".format(filename)],
    deps = [
        "//tensorflow_probability/python/experimental/substrates/numpy/internal",
        "//tensorflow_probability/python/internal/backend/numpy",
    ] + DEPS.get(filename, []),
) for filename in ["hypothesis_testlib"] + FILENAMES]

py_library(
    name = "bijector_test_util",
    srcs = ["bijector_test_util.py"],
    deps = [
        "//tensorflow_probability/python/experimental/substrates/numpy/distributions:normal",
        "//tensorflow_probability/python/experimental/substrates/numpy/distributions:uniform",
    ],
)

[py_test(
    name = filename,
    size = "medium",
    srcs = ["{}.py".format(filename)],
    tags = (["notap"] if filename in TAP_BLACKLIST else []) + ["tfp_numpy"],
    deps = DEPS.get(filename, []) + [
        ":bijector_test_util",
        ":bijectors",
        ":hypothesis_testlib",
        # absl/testing:parameterized dep,
        # hypothesis dep,
        # jax dep,
        # mock dep,
        # numpy dep,
        # scipy dep,
        # six dep,
        "//tensorflow_probability/python/experimental/substrates/numpy/distributions:deprecated_linalg",
        "//tensorflow_probability/python/experimental/substrates/numpy/internal:assert_util",
        "//tensorflow_probability/python/experimental/substrates/numpy/internal:distribution_util",
        "//tensorflow_probability/python/experimental/substrates/numpy/internal:dtype_util",
        "//tensorflow_probability/python/experimental/substrates/numpy/internal:hypothesis_testlib",
        "//tensorflow_probability/python/experimental/substrates/numpy/internal:prefer_static",
        "//tensorflow_probability/python/experimental/substrates/numpy/internal:test_util",
        "//tensorflow_probability/python/internal:name_util",
        "//tensorflow_probability/python/internal/backend/numpy",
    ],
) for filename in TEST_FILENAMES]

py_library(
    name = "bijectors",
    srcs = ["__init__.py"],
    deps = [":{}".format(filename) for filename in FILENAMES],
)
