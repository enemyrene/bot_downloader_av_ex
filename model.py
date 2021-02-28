# -*- coding: utf-8 -*-
#########################################################
# python
import traceback
from datetime import datetime, timedelta
import json
import os

# third-party
from sqlalchemy import or_, and_, func, not_, desc
from sqlalchemy.orm import backref

# sjva 공용
from framework import app, db, path_app_root
from framework.util import Util

#################################################
# 18 아래 join에서 사용하기때문에 반드시 먼저 import 되어야함.. 까먹지 말것
from downloader import ModelDownloaderItem
############################################
# 패키지
from .plugin import P
logger = P.logger
ModelSetting = P.ModelSetting

  
class ModelItem(db.Model):
    __tablename__ = '%s_item' % P.package_name 
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = P.package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)
    reserved = db.Column(db.JSON)

    # 수신받은 데이터 전체
    data = db.Column(db.JSON)

    # 토렌트 정보
    name = db.Column(db.String)
    filename = db.Column(db.String)
    dirname = db.Column(db.String)
    magnet = db.Column(db.String)
    file_count = db.Column(db.Integer)
    total_size = db.Column(db.Integer)
    url = db.Column(db.String)

    # 공용
    av_type = db.Column(db.String)
    title = db.Column(db.String)
    poster = db.Column(db.String)
    code = db.Column(db.String)
    studio = db.Column(db.String)
    genre = db.Column(db.String)
    performer = db.Column(db.String)
    meta_type = db.Column(db.String)
    date = db.Column(db.String)
    
    # 다운로드 정보
    download_status = db.Column(db.String)
    plex_key = db.Column(db.String)
    
    downloader_item_id = db.Column(db.Integer, db.ForeignKey('plugin_downloader_item.id'))
    downloader_item = db.relationship('ModelDownloaderItem')

    download_check_time = db.Column(db.DateTime)
    log = db.Column(db.String)

    plex_info = db.Column(db.JSON)

    # 2 버전 추가
    server_id = db.Column(db.Integer)

    folderid = db.Column(db.String)
    folderid_time = db.Column(db.DateTime)
    share_copy_time = db.Column(db.DateTime)
    share_copy_complete_time = db.Column(db.DateTime)

    
    def __init__(self):
        self.created_time = datetime.now()
        self.download_status = ''
        
    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%m-%d %H:%M:%S') 
        ret['download_check_time'] = self.download_check_time.strftime('%m-%d %H:%M:%S') if self.download_check_time is not None  else None
        ret['downloader_item'] = self.downloader_item.as_dict() if self.downloader_item is not None else None
        ret['folderid_time'] = self.folderid_time.strftime('%m-%d %H:%M:%S') if self.folderid_time is not None  else None
        ret['share_copy_time'] = self.share_copy_time.strftime('%m-%d %H:%M:%S') if self.share_copy_time is not None  else None
        ret['share_copy_complete_time'] = self.share_copy_complete_time.strftime('%m-%d %H:%M:%S') if self.share_copy_complete_time is not None  else None
        return ret
    
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def process_telegram_data(data):
        try:
            if not ModelSetting.get_bool('%s_receive' % data['av_type']):
                return
            magnet = 'magnet:?xt=urn:btih:' + data['t']['hash']
            entity = db.session.query(ModelItem).filter_by(magnet=magnet).first()
            if entity is not None:
                logger.debug('magnet exist') 
                return

            try:
                allow_duplicate2 = ModelSetting.get('%s_allow_duplicate2' % data['av_type'])
                logger.debug('allow_duplicate2 : %s' % allow_duplicate2)
                if allow_duplicate2 == '1' and 'av' in data:
                    entities = db.session.query(ModelItem).filter_by(code=data['av']['code_show']).all()
                    # Max 쿼리로 변경해야함.
                    is_max_size = True
                    for entity in entities:
                        logger.debug('entity.total_size : %s', entity.total_size)
                        if entity.total_size > data['t']['size']:
                            is_max_size = False
                            break
                    if is_max_size:
                        logger.debug('duplicate is_max_size=True: %s', data['av']['code_show'])
                    else:
                        logger.debug('duplicate is_max_size=False: %s', data['av']['code_show'])
                        return
                elif allow_duplicate2 == '2' and 'av' in data:
                    entity = db.session.query(ModelItem).filter_by(code=data['av']['code_show']).first()
                    if entity is not None:
                        logger.debug('duplicate : %s', data['av']['code_show'])
                        return
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                logger.debug('***********')
                logger.debug(data)
                #return


            entity =  ModelItem()
            entity.server_id = data['server_id']
            entity.data = data
            entity.av_type = data['av_type']

            entity.name = data['t']['name']
            entity.total_size = data['t']['size']
            entity.file_count = data['t']['num']
            entity.magnet = magnet
            entity.filename = data['t']['filename']
            entity.dirname = data['t']['dirname']
            entity.url = data['t']['url']

            if 'av' in data:
                entity.title = data['av']['title']
                entity.poster = data['av']['poster']
                entity.code = data['av']['code_show']
                entity.studio = data['av']['studio']
                entity.genre = '|'.join(data['av']['genre'])
                entity.performer = '|'.join(data['av']['performer'])
                entity.meta_type = data['av']['meta']
                entity.date = data['av']['date']

            db.session.add(entity)
            db.session.commit()
            return entity
        except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())   

    
    

    @staticmethod
    def web_list(req):
        try:
            ret = {}
            page = 1
            page_size = 30
            job_id = ''
            search = ''
            if 'page' in req.form:
                page = int(req.form['page'])
            if 'search_word' in req.form:
                search = req.form['search_word']
            option = req.form['option']
            order = req.form['order'] if 'order' in req.form else 'desc'
            av_type = req.form['av_type']
            query = ModelItem.make_query(search=search, option=option, order=order, av_type=av_type)
            count = query.count()
            query = query.limit(page_size).offset((page-1)*page_size)
            logger.debug('ModelItem count:%s', count)
            lists = query.all()
            ret['list'] = [item.as_dict() for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def api_list(req):
        try:
            option = req.args.get('option')
            search = req.args.get('search')
            count = req.args.get('count')
            av_type = req.args.get('type')
            server_id_mod = req.args.get('server_id_mod')
            if count is None or count == '':
                count = 100
            query = ModelItem.make_query(option=option, search=search, av_type=av_type, server_id_mod=server_id_mod)
            query = (query.order_by(desc(ModelItem.id))
                .limit(count)
            )
            lists = query.all()
            return lists
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def make_query(search='', option='all', order='desc', av_type='all', server_id_mod=None):
        query = db.session.query(ModelItem)
        if search is not None and search != '':
            if search.find('|') != -1:
                tmp = search.split('|')
                conditions = []
                for tt in tmp:
                    if tt != '':
                        conditions.append(ModelItem.code.like('%'+tt.strip()+'%') )
                query = query.filter(or_(*conditions))
            elif search.find(',') != -1:
                tmp = search.split(',')
                for tt in tmp:
                    if tt != '':
                        query = query.filter(ModelItem.code.like('%'+tt.strip()+'%'))
            else:
                query = query.filter(or_(ModelItem.code.like('%'+search+'%'), ModelItem.filename.like('%'+search+'%'), ModelItem.performer.like('%'+search+'%')))

        if av_type is not None and av_type != '' and av_type != 'all':
            query = query.filter(ModelItem.av_type == av_type)
        
        if option == 'wait':
            query = query.filter(ModelItem.download_status == '')
        elif option == 'true':
            query = query.filter(ModelItem.download_status.like('true%'), not_(ModelItem.download_status.like('true_only_status%')))
        elif option == 'false':
            query = query.filter(ModelItem.download_status.like('false%'), not_(ModelItem.download_status.like('false_only_status%')))
        elif option == 'true_only_status':
            query = query.filter(ModelItem.download_status.like('true_only_status%'))
        elif option == 'false_only_status':
            query = query.filter(ModelItem.download_status.like('false_only_status%'))
        elif option == 'no':
            query = query.filter(ModelItem.download_status.like('no%'))

        elif option == 'share_received':
            query = query.filter(ModelItem.folderid != None)
        elif option == 'share_no_received':
            query = query.filter(ModelItem.folderid == None)
        elif option == 'share_request_incompleted':
            query = query.filter(ModelItem.share_copy_time != None).filter(ModelItem.share_copy_complete_time == None)
        elif option == 'share_request_completed':
            query = query.filter(ModelItem.share_copy_time != None).filter(ModelItem.share_copy_complete_time != None)


        if order == 'desc':
            query = query.order_by(desc(ModelItem.id))
        else:
            query = query.order_by(ModelItem.id)
        if server_id_mod is not None and server_id_mod != '':
            tmp = server_id_mod.split('_')
            if len(tmp) == 2:
                query = query.filter(ModelBotDownloaderKtvItem.server_id % int(tmp[0]) == int(tmp[1]))
        return query

    @staticmethod
    def remove(id):
        try:
            entity = db.session.query(ModelItem).filter_by(id=id).first()
            if entity is not None:
                db.session.delete(entity)
                db.session.commit()
                return True
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    def get_by_id(id):
        try:
            return db.session.query(ModelItem).filter_by(id=id).first()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def receive_share_data(data):
        try:
            query = db.session.query(ModelItem).filter(ModelItem.server_id == int(data['server_id']))
            query = query.filter(ModelItem.magnet.like('%'+ data['magnet_hash']))
            entity = query.with_for_update().first()
            
            if entity is not None:
                #logger.debug(entity)
                if entity.folderid is not None:
                    return True
                entity.folderid = data['folderid']
                entity.folderid_time = datetime.now()
                db.session.commit()
                module = P.logic.get_module('receive')
                module.process_gd(entity)
                return True
            return False
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False


    @classmethod
    def set_gdrive_share_completed(cls, id):
        entity = cls.get_by_id(id)
        if entity is not None:
            entity.share_copy_complete_time = datetime.now()
            entity.download_status = 'true_gdrive_share_completed'
            entity.save()
            logger.debug('true_gdrive_share_completed %s', id)

    @classmethod
    def get_share_incompleted_list(cls):
        #수동인 True_manual_gdrive_share과 분리 \
        #            .filter(cls.download_status == 'true_gdrive_share')  \
        query = db.session.query(cls) \
            .filter(cls.share_copy_time != None).filter() \
            .filter(cls.share_copy_time > datetime.now() + timedelta(days=-1)) \
            .filter(cls.share_copy_complete_time == None)
        return query.all()           