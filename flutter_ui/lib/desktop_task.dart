import 'bridge.dart';

enum DesktopAction {
  setup('一键配置 MuMu', '正在配置 MuMu…'),
  sync('同步 MuMu', '正在同步 MuMu 学习记录…'),
  export('导出今日复习', '正在用本机记录导出今日复习…');

  const DesktopAction(this.label, this.progress);
  final String label;
  final String progress;
}

const mumuSetupInstructions =
    '1. 安装支持 Android 15 的 Windows 版 MuMu。若多开器没有 Android 15 选项，请先从官网下载最新版。\n\n'
    '2. 在 MuMu 多开器中启动要用的 Android 15 模拟器，并在其中安装「不背单词」5.11.8 x86。\n\n'
    '3. 结束当前学习后再开始配置。助手会检查连接与 App 版本，如需开启 Root，会重启这个模拟器。';

const mumuLocationInstructions =
    '如果还没安装，请先从 MuMu 官网下载安装。\n\n'
    '如果已经安装，请右键 MuMu 桌面图标，点「打开文件所在的位置」，然后在这里选择打开的 MuMu 程序文件夹。';

class TaskUpdate {
  TaskUpdate(Json result, this.newLines)
    : status = result['status'] as String,
      message = result['message'] as String?,
      day = result['day'] as String?,
      recovery = (result['recovery'] as List? ?? const []).cast<String>(),
      adbChecked = result['adb_checked'] as bool?,
      rootChecked = result['root_checked'] as bool?;

  final String status;
  final String? message, day;
  final bool? adbChecked, rootChecked;
  final List<String> newLines, recovery;

  bool get running => status == 'running';
  bool get succeeded => status == 'configured' || status == 'exported';
  bool get showDownloads => recovery.contains('download');
  bool get showLocation => recovery.contains('locate');

  String guidance(DesktopAction action) {
    if (status == 'configured') {
      return '配置完成。打开模拟器里的「不背单词」并登录，然后回来点「同步 MuMu」。';
    }
    if (status == 'app_missing') {
      return message ??
          '请在选中的 Android 15 模拟器里安装「不背单词」5.11.8 x86，登录后重试「${action.label}」。';
    }
    if (status == 'no_records') {
      return message ?? '没有可用的学习记录。请在 App 里完成一组学习，再同步 MuMu。';
    }
    if (status == 'idle') {
      return '后台任务提前结束。请重试「${action.label}」。';
    }
    return message ?? '「${action.label}」未完成。请根据上方日志检查后重试。';
  }
}

/// Handles the worker protocol and cumulative log polling for any desktop task.
class DesktopTasks {
  DesktopTasks(this._call);

  final HostCall _call;

  Future<Json> start(DesktopAction action) async =>
      await _call('start', [action.name]) as Json;
  Future<bool> locateMumu() async => await _call('locate_manager') == true;
  Future<void> openMumuSite() async => _call('download_mumu');

  Stream<TaskUpdate> watch() async* {
    var seen = 0;
    while (true) {
      await Future<void>.delayed(const Duration(milliseconds: 280));
      final result = await _call('poll') as Json;
      final lines = (result['lines'] as List? ?? const []).cast<String>();
      final update = TaskUpdate(result, lines.skip(seen).toList());
      seen = lines.length;
      yield update;
      if (!update.running) return;
    }
  }
}
