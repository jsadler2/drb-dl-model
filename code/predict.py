import os
import argparse
import pyarrow
from RGCN import RGCNModel
import numpy as np
from postproc_utils import predict


parser = argparse.ArgumentParser()
parser.add_argument("-o", "--outdir", help='directory where the output should\
                    be written')
parser.add_argument("-t", "--tag", help='tag to append to end of output files',
                    default='')
parser.add_argument("-d", "--dev", help='whether to only do the analysis on \
                     only half the tst  period', action='store_true')
parser.add_argument('-i', "--input_data_file", help='data file [something].npz')
parser.add_argument('-l', "--logged_q", help='whether the model was trained to\
                    predict the log of discharge', action='store_true')
parser.add_argument("-w", "--weights_dir", help='directory where\
                    trained_weights_{tag}/ is')
parser.add_argument("-u", "--hidden_units", help='number of hidden units',
                    type=int)
args = parser.parse_args()

hidden_size = args.hidden_units
in_data_file = args.input_data_file
outdir = args.outdir
weights_dir = args.weights_dir
halve = args.dev
logged_q = args.logged_q
run_tag = args.tag
if run_tag != '':
    run_tag = f'_{run_tag}'

data = np.load(in_data_file)
model = RGCNModel(hidden_size, 2, A=data['dist_matrix'])

model.load_weights(os.path.join(weights_dir, f'/trained_weights{run_tag}/'))

predict(model, data, halve, 'tst', outdir, run_tag, logged_q)
predict(model, data, halve, 'trn', outdir, run_tag, logged_q)
