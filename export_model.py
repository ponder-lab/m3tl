import os

import tensorflow as tf

from src.bert import modeling

from src.model_fn import BertMultiTask
from src.params import Params

flags = tf.flags

FLAGS = flags.FLAGS

flags.DEFINE_string("problem", "WeiboNER",
                    "Problems to run, for multiproblem, use & to seperate, e.g. WeiboNER&WeiboSegment")
flags.DEFINE_string("model_dir", "",
                    "Model dir. If not specified, will use problem_name + _ckpt")


def optimize_graph(params: Params):

    config = tf.ConfigProto(
        device_count={'GPU': 0}, allow_soft_placement=True)

    init_checkpoint = params.ckpt_dir

    tf.logging.info('build graph...')
    # input placeholders, not sure if they are friendly to XLA
    input_ids = tf.placeholder(
        tf.int32, (None, params.max_seq_len), 'input_ids')
    input_mask = tf.placeholder(
        tf.int32, (None, params.max_seq_len), 'input_mask')
    input_type_ids = tf.placeholder(
        tf.int32, (None, params.max_seq_len), 'segment_ids')

    jit_scope = tf.contrib.compiler.jit.experimental_jit_scope

    with jit_scope():
        features = {}
        features['input_ids'] = input_ids
        features['input_mask'] = input_mask
        features['segment_ids'] = input_type_ids
        model = BertMultiTask(params)
        hidden_feature = model.body(
            features, tf.estimator.ModeKeys.PREDICT)
        pred = model.top(features, hidden_feature,
                         tf.estimator.ModeKeys.PREDICT)

        output_tensors = [pred[k] for k in pred]

        tvars = tf.trainable_variables()

        (assignment_map, initialized_variable_names
         ) = modeling.get_assignment_map_from_checkpoint(tvars, init_checkpoint)

        tf.train.init_from_checkpoint(init_checkpoint, assignment_map)

        tmp_g = tf.get_default_graph().as_graph_def()

    with tf.Session(config=config) as sess:
        tf.logging.info('load parameters from checkpoint...')
        sess.run(tf.global_variables_initializer())
        tf.logging.info('freeze...')
        tmp_g = tf.graph_util.convert_variables_to_constants(
            sess, tmp_g, [n.name[:-2] for n in output_tensors])
    tmp_file = os.path.join(params.ckpt_dir, 'export_model')
    tf.logging.info('write graph to a tmp file: %s' % tmp_file)
    with tf.gfile.GFile(tmp_file, 'wb') as f:
        f.write(tmp_g.SerializeToString())
    return tmp_file


if __name__ == "__main__":
    if FLAGS.model_dir:
        base_dir, dir_name = os.path.split(FLAGS.model_dir)
    else:
        base_dir, dir_name = None, None
    params = Params()
    params.assign_problem(FLAGS.problem,
                          base_dir=base_dir, dir_name=dir_name)
    optimize_graph(params)
    params.to_json()