import sqlite3
import os
import json
import datetime
import math

import pandas as pd
import numpy as np

import windrecorder.utils as utils
from windrecorder.config import config
import windrecorder.files as files

class DBManager:
    def __init__(self):
        self.db_path = config.db_path   # 存放数据库的目录
        self.db_filename_dict = files.get_db_file_path_dict()   # 传入当前db目录下的对应用户的数据库文件列表
        self.db_max_page_result = int(config.max_page_result)  # 最大查询页数
        self.user_name = config.user_name   # 用户名

        # 如果目录为空/没有目录，应该进行初始化
        if self.db_filename_dict is None:
            self.db_main_initialize()



    # 根据传入的时间段取得对应数据库的文件名词典
    def db_get_dbfilename_by_datetime(self, db_query_datetime_start, db_query_datetime_end):
        db_query_datetime_start_YMD = utils.set_full_datetime_to_YYYY_MM_DD(db_query_datetime_start)
        db_query_datetime_end_YMD = utils.set_full_datetime_to_YYYY_MM_DD(db_query_datetime_end)

        result = []
        for key, value in self.db_filename_dict.items():
            if db_query_datetime_start_YMD <= value <= db_query_datetime_end_YMD:
                result.append(key)
        return result


    # ___
    # 初始化对应时间的数据库流程
    def db_main_initialize(self):
        print("——初始化数据库中……")
        # 检查有无最新的数据库
        db_filepath_today = files.get_db_filepath_by_datetime(datetime.datetime.today())
        conn_check = self.db_check_exist(db_filepath_today)

        # 初始化最新的数据库
        self.db_initialize(db_filepath_today)

        return conn_check


    # 初始化数据库：如果内容为空，则创建表初始化
    def db_initialize(self,db_filepath):
        print("——初始化数据库：如果内容为空，则创建表初始化")
        conn = sqlite3.connect(db_filepath)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_text'")

        if c.fetchone() is None:
            print("db is empty, write new table.")
            self.db_create_table(db_filepath)
            now = datetime.datetime.now()
            now_name = now.strftime("%Y-%m-%d_%H-%M-%S")
            now_time = int(utils.date_to_seconds(now_name))
            self.db_update_data(
                now_name + ".mp4",
                '0.jpg',
                now_time,
                'Welcome! Go to Setting and Update your screen recording files.',
                False,
                False,
                'base64'
            )
        else:
            print("db existed and not empty")


    # 重新读取配置文件
    def db_update_read_config(self, config):
        self.db_max_page_result = int(config.max_page_result)


    # 初始化数据库：检查、创建、连接入参数据库对象
    def db_check_exist(self, db_filepath):
        print("——初始化数据库：检查、创建、连接最新的数据库对象")
        is_db_exist = False

        # 检查数据库是否存在
        if not os.path.exists(db_filepath):
            print("db not existed")
            is_db_exist = False
            if not os.path.exists(self.db_path):
                os.mkdir(self.db_path)
                print("db dir not existed, mkdir")
        else:
            is_db_exist = True

        # 连接/创建数据库
        conn = sqlite3.connect(db_filepath)
        conn.close()
        return is_db_exist


    # 创建表
    def db_create_table(self, db_filepath):
        print("——创建表")
        conn = sqlite3.connect(db_filepath)
        conn.execute('''CREATE TABLE video_text  
                   (videofile_name VARCHAR(100),
                   picturefile_name VARCHAR(100),
                   videofile_time INT, 
                   ocr_text TEXT,
                   is_videofile_exist BOOLEAN,
                   is_picturefile_exist BOOLEAN,
                   thumbnail TEXT);''')
        conn.close()


    # 插入数据
    def db_update_data(self, videofile_name, picturefile_name, videofile_time, ocr_text, is_videofile_exist,
                       is_picturefile_exist, thumbnail):
        print("——插入数据")
        # 使用方法：db_update_data(db_filepath,'video1.mp4','iframe_0.jpg', 120, 'text from ocr', True, False)

        # 获取插入时间，取得对应的数据库      
        insert_db_datetime = utils.set_full_datetime_to_YYYY_MM_DD(utils.seconds_to_datetime(videofile_time))
        db_filepath = files.get_db_filepath_by_datetime(insert_db_datetime)   # 直接获取对应时间的数据库路径

        conn = sqlite3.connect(db_filepath)
        c = conn.cursor()

        c.execute(
            "INSERT INTO video_text (videofile_name, picturefile_name, videofile_time, ocr_text, is_videofile_exist, is_picturefile_exist, thumbnail) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (videofile_name, picturefile_name, videofile_time, ocr_text, is_videofile_exist, is_picturefile_exist,
             thumbnail))
        conn.commit()
        conn.close()


    # 查询关键词数据，返回完整的结果 dataframe
    def db_search_data(self, keyword_input, date_in, date_out, keyword_input_exclude=""):
        # 返回值：关于结果的所有数据 df，所有结果的总行数
        print("——查询关键词数据")
        # 初始化查询数据
        # date_in/date_out : 类型为datetime.datetime
        self.db_update_read_config(config)
        date_in_ts = int(utils.date_to_seconds(date_in.strftime("%Y-%m-%d_00-00-00")))
        date_out_ts = int(utils.date_to_seconds(date_out.strftime("%Y-%m-%d_23-59-59")))

        # 获得对应时间段下涉及的所有数据库
        datetime_start = utils.seconds_to_datetime(date_in_ts)
        datetime_end = utils.seconds_to_datetime(date_out_ts)
        query_db_name_list = self.db_get_dbfilename_by_datetime(datetime_start,datetime_end)

        # 遍历查询所有数据库信息
        df_all = pd.DataFrame()
        row_count = 0
        for key in query_db_name_list:
            db_filepath = os.path.join(self.db_path, key)   # 构建完整路径
            print(f"- Querying {db_filepath}")

            # 连接数据库
            conn = sqlite3.connect(db_filepath)

            # 查询总结果数量，获得页数
            c = conn.cursor()

            # 构建sql
            keywords = keyword_input.split()
            query = f"SELECT * FROM video_text WHERE "
            if keyword_input:   # 不为空时
                conditions = []
                for keyword in keywords:
                    conditions.append(f"ocr_text LIKE '%{keyword}%'")
                query += " AND ".join(conditions)
            else:
                query += f"ocr_text LIKE '%{keyword_input}%'"
            
            if keyword_input_exclude:
                query += " AND "
                keywords_exclude = keyword_input_exclude.split()
                conditions = []
                for keyword_exclude in keywords_exclude:
                    conditions.append(f"ocr_text NOT LIKE '%{keyword_exclude}%'")
                query += " AND ".join(conditions)

            query += f" AND videofile_time BETWEEN {date_in_ts} AND {date_out_ts}"

            df = pd.read_sql_query(query, conn)

            # 查询所有关键词和时间段下的结果
            # if keyword_input_exclude:
            #     df = pd.read_sql_query(f"""
            #                           SELECT * FROM video_text 
            #                           WHERE ocr_text LIKE '%{keyword_input}%' 
            #                           AND ocr_text NOT LIKE '%{keyword_input_exclude}%'
            #                           AND videofile_time BETWEEN {date_in_ts} AND {date_out_ts} """
            #                            , conn)
            # else:
            #     df = pd.read_sql_query(f"""
            #                           SELECT * FROM video_text 
            #                           WHERE ocr_text LIKE '%{keyword_input}%' 
            #                           AND videofile_time BETWEEN {date_in_ts} AND {date_out_ts} """
            #                            , conn)
                
            df_all = pd.concat([df_all, df], ignore_index=True)
            row_count = row_count + len(df_all)
            conn.close()

        page_count_all = int(math.ceil(int(row_count)/int(self.db_max_page_result)))

        return df_all, row_count, page_count_all


    # 拿到完整df后进行翻页检索操作
    def db_search_data_page_turner(self, df, page_index):
        # page_index 从 1 计起
        row_count = len(df)   # 总行数
        page_count = int(math.ceil(int(row_count)/int(self.db_max_page_result)))   # 根据结果与用户配置，计算需要多少页读取
        if page_count <= 1:
            page_count = 1
        
        row_start_index = 0 + (page_index-1)*self.db_max_page_result
        row_end_index = row_start_index + self.db_max_page_result
        
        df_current_page = df[row_start_index:row_end_index]

        # 返回当前页的dataframe
        return df_current_page


    # 优化搜索数据结果的展示
    def db_refine_search_data(self, df):
        print("——优化搜索数据结果的展示")
        df.drop('picturefile_name', axis=1, inplace=True)
        df.drop('is_picturefile_exist', axis=1, inplace=True)

        df.insert(1, 'time_stamp', df['videofile_time'].apply(utils.seconds_to_date))
        # df.drop('videofile_time', axis=1, inplace=True)

        df.insert(len(df.columns) - 1, 'videofile_name', df.pop('videofile_name'))
        df.insert(len(df.columns) - 1, 'videofile_time', df.pop('videofile_time'))
        # df['is_videofile_exist'] = df['is_videofile_exist'].astype(str)

        df['thumbnail'] = 'data:image/png;base64,' + df['thumbnail']
        df.insert(0, 'thumbnail', df.pop('thumbnail'))

        return df


    # 列出所有数据
    def db_print_all_data(self):
        print("——列出所有数据库的所有数据")
        # 获取游标
        # 使用SELECT * 从video_text表查询所有列的数据
        # 使用fetchall()获取所有结果行
        # 遍历结果行,打印出每一行
        full_db_name_ondisk_dict = files.get_db_file_path_dict()
        for key, value in full_db_name_ondisk_dict.items():
            db_filepath = os.path.join(self.db_path, key)

            conn = sqlite3.connect(db_filepath)
            c = conn.cursor()
            c.execute("SELECT * FROM video_text")
            rows = c.fetchall()
            for row in rows:
                print(row)
            conn.close()


    # 查询全部数据库一共有多少行
    def db_num_records(self):
        print("——查询全部数据库一共有多少行")
        full_db_name_ondisk_dict = files.get_db_file_path_dict()
        rows_count_all = 0
        for key, value in full_db_name_ondisk_dict.items():
            db_filepath = os.path.join(self.db_path, key)
            conn = sqlite3.connect(db_filepath)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM video_text")
            rows_count = c.fetchone()[0]
            conn.close()
            rows_count_all += rows_count
            print(f"db_filepath: {db_filepath}, rows_count: {rows_count}")
        print(f"rows_count_all: {rows_count_all}")
        return rows_count_all


    # 获取表内最新的记录时间
    def db_latest_record_time(self):
        full_db_name_ondisk_dict = files.get_db_file_path_dict()
        db_name_ondisk_lastest = files.get_lastest_datetime_key(full_db_name_ondisk_dict)
        db_filepath = os.path.join(self.db_path, db_name_ondisk_lastest)

        conn = sqlite3.connect(db_filepath)
        c = conn.cursor()

        c.execute("SELECT MAX(videofile_time) FROM video_text")
        max_time = c.fetchone()[0]
        conn.close()
        return max_time #返回时间戳
    

    # 获取表内最早的记录时间
    def db_first_earliest_record_time(self):
        full_db_name_ondisk_dict = files.get_db_file_path_dict()
        db_name_ondisk_lastest = files.get_earliest_datetime_key(full_db_name_ondisk_dict)
        db_filepath = os.path.join(self.db_path, db_name_ondisk_lastest)

        conn = sqlite3.connect(db_filepath)
        c = conn.cursor()

        c.execute("SELECT MIN(videofile_time) FROM video_text")
        min_time = c.fetchone()[0]
        conn.close()
        return min_time #返回时间戳
    

    # 回滚操作：删除输入视频文件名相关的所有条目
    def db_rollback_delete_video_refer_record(self,videofile_name):
        print(f"移除{videofile_name}相关条目")
        # 根据文件名定位数据库文件地址
        db_filepath = files.get_db_filepath_by_datetime(utils.set_full_datetime_to_YYYY_MM_DD(utils.date_to_datetime(os.path.splitext(videofile_name)[0])))

        conn = sqlite3.connect(db_filepath)
        c = conn.cursor()

        # 构建SQL语句，使用LIKE操作符进行模糊匹配
        sql = f"DELETE FROM video_text WHERE videofile_name LIKE '%{videofile_name}%'"
        # 精确匹配的方式
        # sql = f"DELETE FROM video_text WHERE videofile_name = '{videofile_name}'"
        c.execute(sql)
        conn.commit()
        conn.close()

    
    # 获取一个时间段内，按时间戳等均分的几张缩略图
    def db_get_day_thumbnail(self,date_in,date_out,back_pic_num):
        df,all_result_counts,_ = self.db_search_data("",date_in,date_out)

        gap_num = int(all_result_counts/back_pic_num)

        if all_result_counts < back_pic_num:
            print("-all_result_counts < back_pic_num")
            return None

        # 获取df内最早与最晚记录时间
        time_min = df['videofile_time'].min()
        time_max = df['videofile_time'].max()

        # 计算均分时间间隔
        time_range = time_max - time_min
        time_gap = int(time_range / back_pic_num)

        # 生成理想的时间间隔表
        timestamp_list = [time_min + i * time_gap for i in range(back_pic_num + 1)]

        # 寻找最近的时间戳数据
        closest_timestamp_result = []
        for timestamp in timestamp_list:
            closest_timestamp = df[
                np.abs(df['videofile_time'] - timestamp) <= 300 # 差距阈值:second
            ]['videofile_time'].max()
            if closest_timestamp is None:
                closest_timestamp = 0
            closest_timestamp_result.append(closest_timestamp)

        # 返回对应的缩略图数据
        thumbnails_result = []
        for timestamp in closest_timestamp_result:
            if timestamp == 0:
                thumbnails_result.append(None)
            else:
                thumbnail = df[df['videofile_time'] == timestamp]['thumbnail'].values
                if len(thumbnail) > 0:
                    thumbnails_result.append(thumbnail[0])
                else:
                    thumbnails_result.append(None)

        return thumbnails_result

        # 平均地获取结果图片，而不是平均地按时间分
        img_list = []
        thumbnails_result = df['thumbnail'].tolist()
        rows = len(df)

        for i in range(0,rows,gap_num):
            img_list.append(thumbnails_result[i])

        return img_list


# dbManager = DBManager(
#     config.db_path,
#     files.get_db_file_path_list(),
#     int(config.max_page_result)
# )
