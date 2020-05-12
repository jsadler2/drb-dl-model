import json
import pandas as pd
import numpy as np


def post_process(y_pred, dates, ids):
    """
    post process y data (reshape and make into pandas DFs)
    :param y_pred:[numpy array] array of predictions [nbatch, seq_len, n_out]
    :param dates:[numpy array] array of dates [nbatch, seq_len, n_out]
    :param ids: [numpy array] array of seg_ids [nbatch, seq_len, n_out]
    :return:[pd dataframe] df with cols
    ['date', 'seg_id_nat', 'temp_c', 'discharge_cms]
    """
    y_pred = np.reshape(y_pred, [y_pred.shape[0]*y_pred.shape[1],
                                 y_pred.shape[2]])

    dates = np.reshape(dates, [dates.shape[0]*dates.shape[1], dates.shape[2]])
    ids = np.reshape(ids, [ids.shape[0]*ids.shape[1], ids.shape[2]])
    df_preds = pd.DataFrame(y_pred, columns=['temp_c', 'discharge_cms'])
    df_dates = pd.DataFrame(dates, columns=['date'])
    df_ids = pd.DataFrame(ids, columns=['seg_id_nat'])
    df = pd.concat([df_dates, df_ids, df_preds], axis=1)
    return df


def take_first_half(df):
    """
    filter out the second half of the dates in the predictions. this is to
    retain a "test" set of the i/o data for evaluation
    :param df:[pd dataframe] df of predictions or observations cols ['date',
    'seg_id_nat', 'temp_c', 'discharge_cms']
    :return: [pd dataframe] same cols as input, but only the first have of dates
    """
    df.set_index('date', inplace=True)
    df.sort_index(inplace=True)
    unique_dates = df.index.unique()
    halfway_date = unique_dates[int(len(unique_dates)/2)]
    df_first_half = df.loc[:halfway_date]
    df_first_half.reset_index(inplace=True)
    return df_first_half


def unscale_output(y_scl, y_std, y_mean, logged_q=False):
    """
    unscale output data given a standard deviation and a mean value for the
    outputs
    :param y_scl: [pd dataframe] scaled output data (predicted or observed)
    :param y_std:[numpy array] array of standard deviation of variables [n_out]
    :param y_mean:[numpy array] array of variable means [n_out]
    :param logged_q: [bool] whether the model predicted log of discharge. if
    true, the exponent of the discharge will be executed
    :return:
    """
    data_cols = ['temp_c', 'discharge_cms']
    yscl_data = y_scl[data_cols]
    y_unscaled_data = (yscl_data * y_std) + y_mean
    y_scl[data_cols] = y_unscaled_data
    if logged_q:
        y_scl['discharge_cms'] = np.exp(y_scl['discharge_cms'])
    return y_scl


def rmse_masked(y_true, y_pred):
    """
    Compute cost as RMSE with masking (the tf.where call replaces pred_s-y_s
    with 0 when y_s is nan; num_y_s is a count of just those non-nan
    observations) so we're only looking at predictions with corresponding
    observations available
    (credit: @aappling-usgs)
    :param data: [tensor] true (observed) y values. these may have nans and 
    sample weights
    :param y_pred: [tensor] predicted y values
    :return: rmse (one value for each training sample)
    """
    # count the number of non-nans
    num_y_true = np.sum(~np.isnan(y_true))
    zero_or_error = np.where(np.isnan(y_true),
                             0,
                             y_pred - y_true)
    sum_squared_errors = np.sum(zero_or_error ** 2)
    rmse_loss = np.sqrt(sum_squared_errors / num_y_true)
    return rmse_loss

  
def nse(y_true, y_pred):
    """
    compute the nash-sutcliffe model efficiency coefficient
    :param y_true:
    :param y_pred:
    :return:
    """
    q_mean = np.nanmean(y_true)
    numerator = np.nansum((y_true-y_pred)**2)
    denominator = np.nansum((y_true - q_mean)**2)
    return 1 - (numerator/denominator)


def predict(trained_model, io_data, half_tst, tag, outdir, run_tag='',
            logged_q=False):
    """
    use trained model to make predictions and then evaluate those predictions.
    nothing is returned but three files are saved an rmse_flow, rmse_temp, and
    predictions feather file.
    :param trained_model:[tf model] model with trained weights loaded
    :param io_data:[dict] dictionary with all the io data for x_trn, y_trn,
    y_tst, etc.
    :param half_tst: [bool] whether or not to halve the testing data so some
    can be held out
    :param tag: [str] must be 'trn' or 'tst'; whether you want to predict for
    the train or the dev period
    :param outdir: [str] the directory where the output data should be stored
    :param run_tag: [str] the tag to append to the output files
    :param logged_q: [str] whether the discharge was logged in training. if True
    the exponent of the discharge will be taken in the model unscaling
    :return:[none]
    """
    # evaluate training
    if tag == 'trn' or tag == 'tst':
        pass
    else:
        raise ValueError('tag arg needs to be "trn" or "tst"')

    num_segs = io_data['dist_matrix'].shape[0]
    y_pred = trained_model.predict(io_data[f'x_{tag}'],
                                   batch_size=num_segs)
    y_pred_pp = post_process(y_pred, io_data[f'dates_{tag}'],
                             io_data[f'ids_{tag}'])

    y_pred_pp = unscale_output(y_pred_pp, io_data['y_trn_obs_std'],
                               io_data['y_trn_obs_mean'], logged_q)

    if half_tst and tag == 'tst':
        y_pred_pp = take_first_half(y_pred_pp)

    y_pred_pp.to_feather(f'{outdir}{tag}_preds{run_tag}.feather')


def fmt_preds_obs(pred_file, obs_file, variable):
    """
    combine predictions and observations in one dataframe
    :param pred_file:[str] filepath to the predictions file 
    :param obs_file:[str] filepath to the observations file
    :param variable: [str] variable (either 'discharge_cms' or 'temp_c')
    """
    pred_data = pd.read_feather(pred_file)
    pred_data.set_index(['date', 'seg_id_nat'], inplace=True)
    obs = pd.read_csv(obs_file, parse_dates=['date'],
                      infer_datetime_format=True,
                      index_col=['date', 'seg_id_nat'])
    obs = obs[[variable]]
    obs.columns = ['obs']
    preds = pred_data[[variable]]
    preds.columns = ['pred']
    combined = preds.join(obs)
    return combined


def calc_metrics(pred_file, obs_file_temp, obs_file_flow, outdir, tag, run_tag):
    temp_data = fmt_preds_obs(pred_file, obs_file_temp, 'temp_c')
    flow_data = fmt_preds_obs(pred_file, obs_file_flow, 'discharge_cms')
    temp_data.reset_index().to_feather('fmt_temp.feather')

    rmse_temp = rmse_masked(temp_data['obs'], temp_data['pred'])
    rmse_flow = rmse_masked(flow_data['obs'], flow_data['pred'])
    nse_temp = nse(temp_data['obs'], temp_data['pred'])
    nse_flow = nse(flow_data['obs'], flow_data['pred'])

    metrics_data = {'rmse_temp': str(rmse_temp), 'rmse_flow': str(rmse_flow),
                    'nse_temp': str(nse_temp), 'nse_flow': str(nse_flow)}
    # save files
    with open(f'{outdir}{tag}_metrics{run_tag}.json', 'w') as f:
        json.dump(metrics_data, f)


def calc_reach_specific_metrics(df):
    if df['obs'].count() > 10:
        reach_rmse = rmse_masked(df['obs'], df['pred'])
        reach_nse = nse(df['obs'].values, df['pred'].values)
        return pd.Series(dict(rmse=reach_rmse, nse=reach_nse))
    else:
        return pd.Series(dict(rmse=np.nan, nse=np.nan))


def reach_specific_metrics(pred_file, obs_file_temp, obs_file_flow, outdir, tag,
                           run_tag):
    temp_data = fmt_preds_obs(pred_file, obs_file_temp, 'temp_c')
    flow_data = fmt_preds_obs(pred_file, obs_file_flow, 'discharge_cms')
    reach_metrics_temp = temp_data.groupby('seg_id_nat').apply(calc_reach_specific_metrics).reset_index()
    reach_metrics_flow = flow_data.groupby('seg_id_nat').apply(calc_reach_specific_metrics).reset_index()
    reach_metrics_temp.to_feather(f'{outdir}{tag}_temp_reach_metrics{run_tag}.feather')
    reach_metrics_flow.to_feather(f'{outdir}{tag}_flow_reach_metrics{run_tag}.feather')
#
# calc_metrics('../../experiments/A/Av1/A4/tst_preds.feather', '../../data/obs_temp.feather', '../../data/obs_flow.feather', '', '', '')
