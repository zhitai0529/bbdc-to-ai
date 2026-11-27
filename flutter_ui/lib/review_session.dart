import 'bridge.dart';

typedef Draft = ({String original, String text});

/// View data and per-day drafts, independent of widgets and MuMu jobs.
class ReviewSession {
  ReviewSession(this._call);

  final HostCall _call;
  final _drafts = <String, Draft>{};
  Json? data;
  String? _pinnedDay;

  String get _key => '${data?['folder']}\n${data?['day']}';
  Draft? get currentDraft => _drafts[_key];
  String get content => currentDraft?.text ?? data?['prompt'] ?? '';
  bool get hasDrafts => _drafts.isNotEmpty;
  bool get hasCurrentDraft => currentDraft != null;
  String? get pinnedDay => _pinnedDay;
  String get loadStatus {
    final current = data!;
    final warning = current['warning'] as String?;
    if (warning != null && warning.isNotEmpty) return warning;
    final day = current['day'];
    if (current['stats'] != null) return '已载入 $day 的本机记录。';
    if (current['prompt'] != null) return '已找到 $day 的复习文件，可在「复习预览」中打开。';
    if (day != current['today']) return '本机没有 $day 的学习记录，请切换日期查看其他记录。';
    return '本机没有 $day 的学习记录。可切换日期查看历史，或点「同步 MuMu」获取记录。';
  }

  Future<({String? warning, bool export})> initialize() async {
    final result = await _call('initialize') as Json;
    data = result['data'] as Json;
    return (
      warning: result['warning'] as String?,
      export: result['export'] == true,
    );
  }

  Future<void> selectDay(String? day, {bool? pin}) async {
    data = await _call('select_day', [day]) as Json;
    if (pin != null) _pinnedDay = pin ? day : null;
  }

  void discardCurrentDraft(Draft approved) {
    if (currentDraft == approved) _drafts.remove(_key);
  }

  void edit(String text) {
    final current = data?['prompt'] as String?;
    final original = _drafts[_key]?.original ?? current;
    if (original == null) return;
    if (text == current) {
      _drafts.remove(_key);
    } else {
      _drafts[_key] = (original: original, text: text);
    }
  }

  Future<bool> saveDraft() async {
    final key = _key;
    final draft = _drafts[key];
    if (draft == null) return false;
    final day = data!['day'] as String;
    await _call('save_prompt', [day, draft.original, draft.text]);
    _drafts.remove(key);
    await selectDay(day);
    return true;
  }

  Future<bool> changeFolder() async {
    if (await _call('change_folder') != true) return false;
    await selectDay(null, pin: false);
    return true;
  }

  Future<void> saveReviewLevel(String level) async {
    await _call('save_review_level', [level]);
    data = {...data!, 'review_level': level};
  }

  Future<void> openFolder() async => _call('open_folder');
}
