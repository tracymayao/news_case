# 使用蓝图对象
from flask import session, render_template, current_app, jsonify, request, g

from info import constants, db
from info.models import User, Category, News, CommentLike, Comment
from info.utils.commons import login_required
from info.utils.response_code import RET
from . import news_blue

import hashlib
from werkzeug.security import generate_password_hash,check_password_hash


# 首页模板数据加载
@news_blue.route('/')
@login_required
def index():
    """
    首页：
        右上角用户信息展示：检查用户登录状态

    :return:
    """
    user = g.user

    # 新闻分类数据展示
    try:
        categories = Category.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询新闻分类数据失败')
    # 判断查询结果
    if not categories:
        return jsonify(errno=RET.NODATA,errmsg='无新闻分类数据')
    category_list = []
    # 遍历查询新闻分类结果,存入列表
    for category in categories:
        category_list.append(category.to_dict())

    # 新闻点击排行
    try:
        news_list = News.query.order_by(News.clicks.desc()).limit(constants.CLICK_RANK_MAX_NEWS)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询新闻排行数据失败')
    if not news_list:
        return jsonify(errno=RET.NODATA,errmsg='无新闻排行数据')
    news_click_list = []
    for news in news_list:
        news_click_list.append(news.to_dict())


    data = {
        'user_info':user.to_dict() if user else None,
        'category_list':category_list,
        'news_click_list':news_click_list
    }

    return render_template('news/index.html',data=data)


@news_blue.route('/news_list')
def get_news_list():
    """
    新闻列表
    1、获取参数，cid，page，per_page
    2、检查参数的类型
    3、根据cid来查询mysql数据库,最新
    如果用户选择的是最新，默认查询所有新闻数据
    News.query.filter().order_by(News.create_time.desc()).paginate(page,per_page,False)
    News.query.filter(News.category_id==cid).order_by(News.create_time.desc()).paginate(page,per_page,False)
    4、获取分页后的数据
    总页数、当前页数、新闻列表
    5、返回结果
    :return:
    """
    # 获取参数
    cid = request.args.get('cid','1')
    page = request.args.get('page','1')
    per_page = request.args.get('per_page','10')
    # 转换参数的数据类型
    try:
        cid,page,per_page = int(cid),int(page),int(per_page)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR,errmsg='参数格式错误')
    # 定义容器，存储查询的过滤条件
    filters = []
    # 判断分类id如果不是最新
    if cid > 1:
        filters.append(News.category_id == cid)
    # 使用过滤条件查询mysql，按照新闻发布时间排序
    print(filters)
    try:
        # *filters表示python中拆包，News.category_id==cid，*filters里面存储的是sqlalchemy对象
        # 在python中测试添加的数据为True或False
        paginate = News.query.filter(*filters).order_by(News.create_time.desc()).paginate(page,per_page,False)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询新闻数据失败')
    # 获取分页后的数据
    news_list = paginate.items
    total_page = paginate.pages
    current_page = paginate.page
    # 定义容器，存储查询到的新闻数据
    news_dict_list = []
    for news in news_list:
        news_dict_list.append(news.to_dict())
    data = {
        'news_dict_list':news_dict_list,
        'total_page':total_page,
        'current_page':current_page
    }
    # 返回数据
    return jsonify(errno=RET.OK,errmsg='OK',data=data)

@news_blue.route('/<int:news_id>')
@login_required
def get_news_detail(news_id):
    """
    新闻详情
        用户数据展示
        点击排行展示
        新闻数据展示
    :param news_id:
    :return:
    """
    # 从登录验证装饰器中获取用户信息
    user = g.user
    # 新闻点击排行
    try:
        news_list = News.query.order_by(News.clicks.desc()).limit(constants.CLICK_RANK_MAX_NEWS)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询新闻排行数据失败')
    if not news_list:
        return jsonify(errno=RET.NODATA, errmsg='无新闻排行数据')
    news_click_list = []
    for news in news_list:
        news_click_list.append(news.to_dict())

    # 新闻详情数据
    try:
        news = News.query.get(news_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询新闻详情数据失败')
    if not news:
        return jsonify(errno=RET.NODATA,errmsg='无新闻详情数据')
    # 收藏或取消收藏的标记
    is_collected = False
    # 判断用户是否收藏过,用户登录后才能显示该新闻是否收藏
    if user and news in g.user.collection_news:
        is_collected = True

    # 新闻评论信息展示

    try:
        comments = Comment.query.filter(Comment.news_id == news_id).order_by(Comment.create_time.desc()).all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询评论信息失败')
    # 评论点赞id
    comment_like_ids = []
    # 获取当前登录用户的所有评论的id，
    if user:
        try:
            comment_ids = [comment.id for comment in comments]
            # 再查询点赞了哪些评论
            comment_likes = CommentLike.query.filter(CommentLike.comment_id.in_(comment_ids),
                                                     CommentLike.user_id == g.user.id).all()
            # 遍历点赞的评论数据
            comment_like_ids = [comment_like.comment_id for comment_like in comment_likes]
        except Exception as e:
            current_app.logger.error(e)
    comment_dict_list = []
    for comment in comments:
        comment_dict = comment.to_dict()
        # 如果未点赞
        comment_dict['is_like'] = False
        # 如果点赞
        if comment.id in comment_like_ids:
            comment_dict['is_like'] = True
        comment_dict_list.append(comment_dict)

    data = {
        'user_info': user.to_dict() if user else None,
        'news_click_list': news_click_list,
        'news_detail':news.to_dict(),
        'is_collected':is_collected,
        "comments": comment_dict_list
    }

    return render_template('news/detail.html',data=data)

@news_blue.route("/news_collect",methods=['POST'])
@login_required
def news_collect():
    """
    新闻收藏和取消收藏
    1、获取参数，news_id,action[collect,cancel_collect]
    2、检查参数的完整性
    3、转换news_id参数的数据类型
    4、检查action参数的范围
    5、查询mysql确认新闻的存在
    6、校验查询结果
    7、判断用户选择的是收藏，还要判断用户之前未收藏过
    user.collection_news.append(news)
    如果是取消收藏
    user.collection_news.remove(news)
    8、提交数据mysql
    9、返回结果


    :return:
    """
    # 从登录验证装饰器中获取用户信息
    user = g.user
    # 判断用户是否登录
    if not user:
        return jsonify(errno=RET.SESSIONERR,errmsg='用户未登录')

    news_id = request.json.get('news_id')
    action = request.json.get('action')
    # 检查参数的完整性
    if not all([news_id,action]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    # 转换newsid数据类型
    try:
        news_id = int(news_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR,errmsg='参数类型错误')
    # 检查action参数的范围
    if action not in ['collect','cancel_collect']:
        return jsonify(errno=RET.PARAMERR,errmsg='参数范围错误')
    # 根据新闻id查询数据
    try:
        news = News.query.get(news_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询数据失败')
    # 判断查询结果
    if not news:
        return jsonify(errno=RET.NODATA,errmsg='无新闻数据')
    # 如果用户选择的是收藏
    if action == 'collect':
        # 该新闻用户之前未收藏
        if news not in user.collection_news:
            user.collection_news.append(news)
    else:
        user.collection_news.remove(news)
    # 提交数据
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存数据失败')
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK')


@news_blue.route("/news_comment",methods=['POST'])
@login_required
def news_comment():
    """
    新闻评论
    1、尝试获取用户信息，如果用户未登录，直接结束程序
    2、获取参数，news_id,comment,parent_id
    3、检查参数的完整性，news_id,comment
    4、把news_id转换数据类型，如果parent_id存在
    5、查询数据库，确认新闻的存在
    6、保存评论信息
    coments = Comment()
    7、提交数据到数据库
    8、返回结果

    :return:
    """
    user = g.user
    if not user:
        return jsonify(errno=RET.SESSIONERR,errmsg='用户未登录')
    # 获取参数
    news_id = request.json.get('news_id')
    content = request.json.get('comment')
    parent_id = request.json.get('parent_id')
    # 检查参数的完整性
    if not all([news_id,content]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    # 转换参数的数据类型
    try:
        news_id = int(news_id)
        if parent_id:
            parent_id = int(parent_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR,errmsg='参数类型错误')
    # 查询数据库，确认新闻的存在
    try:
        news = News.query.get(news_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询新闻数据失败')
    # 判断查询结果
    if not news:
        return jsonify(errno=RET.NODATA,errmsg='新闻不存在')
    # 构造模型类对象，存储评论信息
    comments = Comment()
    comments.user_id = user.id
    comments.news_id = news_id
    comments.content = content
    if parent_id:
        comments.parent_id = parent_id
    try:
        db.session.add(comments)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存数据失败')
    # 返回结果
    return jsonify(errno=RET.OK,errmsg="OK",data=comments.to_dict())

@news_blue.route('/comment_like',methods=['POST'])
@login_required
def comment_like():
    """
    点赞或取消点赞
    1、获取用户登录信息
    2、获取参数，comment_id,action
    3、检查参数的完整性
    4、判断action是否为add，remove
    5、把comment_id转成整型
    6、根据comment_id查询数据库
    7、判断查询结果
    8、判断行为是点赞还是取消点赞
    9、如果为点赞，查询改评论，点赞次数加1，否则减1
    10、提交数据
    11、返回结果

    :return:
    """
    user = g.user
    comment_id = request.json.get('comment_id')
    action = request.json.get('action')
    if not all([comment_id,action]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    if action not in ['add','remove']:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    try:
        comment_id = int(comment_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='参数错误')
    try:
        comments = Comment.query.get(comment_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='保存数据失败')
    if not comments:
        return jsonify(errno=RET.NODATA,errmsg='评论不存在')
    # 如果选择的是点赞
    if action == 'add':
        comment_like_model = CommentLike.query.filter(CommentLike.user_id == user.id,CommentLike.comment_id== comment_id).first()
        # 判断查询结果，如果没有点赞过
        if not comment_like_model:
            comment_like_model = CommentLike()
            comment_like_model.user_id = user.id
            comment_like_model.comment_id = comment_id
            # 把数据提交给数据库会话对象，点赞次数加1
            db.session.add(comment_like_model)
            comments.like_count += 1
    # 如果取消点赞
    else:
        comment_like_model = CommentLike.query.filter(CommentLike.user_id==user.id,CommentLike.comment_id==comment_id).first()
        if comment_like_model:
            db.session.delete(comment_like_model)
            comments.like_count -= 1

    try:
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存数据失败')

    return jsonify(errno=RET.OK,errmsg='OK')


@news_blue.route('/followed_user',methods=['POST'])
@login_required
def followed_user():
    """
    关注与取消关注
    1、获取用户信息,如果未登录直接返回
    2、获取参数，user_id和action
    3、检查参数的完整性
    4、校验参数，action是否为followed，unfollow
    5、根据用户id获取被关注的用户
    6、判断获取结果
    7、根据对应的action执行操作，关注或取消关注
    8、返回结果
    :return:
    """
    user = g.user
    if not user:
        return jsonify(errno=RET.SESSIONERR,errmsg='用户未登录')
    user_id = request.json.get('user_id')
    action = request.json.get('action')
    if not all([user_id,action]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    if action not in ['follow','unfollow']:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    try:
        other = User.query.get(user_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询数据失败')
    if not other:
        return jsonify(errno=RET.NODATA,errmsg='无用户数据')
    # 如果选择关注
    if action == 'follow':
        if other not in user.followed:
            user.followed.append(other)
        else:
            return jsonify(errno=RET.DATAEXIST,errmsg='当前用户已被关注')
    # 取消关注
    else:
        if other in user.followed:
            user.followed.remove(other)

    return jsonify(errno=RET.OK,errmsg='OK')
















# 项目favicon.ico文件的加载
@news_blue.route('/favicon.ico')
def favicon():
    """
    http://127.0.0.1:5000/favicon.ico
    实现/favicon.ico路径下的图标加载
    1、favicon图标的加载，不是每次请求都加载，是浏览器默认实现的，如果有缓存，必须要清除缓存，
    2、把浏览器彻底关闭，重启浏览器。
    :return:
    """
    # 使用current_app调用flask内置的函数，发送静态文件给浏览器，实现logo图标的加载
    return current_app.send_static_file('news/favicon.ico')