import 'package:flutter/material.dart';
import 'bridge.dart';
import 'widgets.dart';

class HistoryPage extends StatelessWidget {
  const HistoryPage(this.data, {super.key});
  final Json data;
  @override
  Widget build(BuildContext context) {
    final repeats = (data['repeats'] as List).cast<Json>(),
        hard = (data['errors'] as List).cast<Json>(),
        codes = (data['unknown'] as List).cast<Json>();
    final fromExport = data['stats']?['export_summary'] == true;
    Widget table(
      List<String> headings,
      List<List<Object?>> rows,
      String empty,
    ) {
      if (rows.isEmpty) return Empty(empty);
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columnSpacing: 30,
          headingRowHeight: 38,
          dataRowMinHeight: 38,
          dataRowMaxHeight: 52,
          columns: [for (final h in headings) DataColumn(label: Text(h))],
          rows: [
            for (final row in rows)
              DataRow(
                cells: [
                  for (final value in row)
                    DataCell(SelectableText(value?.toString() ?? '—')),
                ],
              ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Section(
          '跨天反复模糊或答错',
          Icons.repeat_rounded,
          table(
            ['单词', '出现学习日数', '最近一次'],
            [
              for (final r in repeats) [r['word'], r['days'], r['last_day']],
            ],
            '窗口内暂无跨天重复记录。',
          ),
          action: Text('近 ${data['window']} 天'),
        ),
        const SizedBox(height: 14),
        Section(
          '当日顽固词',
          Icons.local_fire_department_outlined,
          table(
            ['单词', '本轮错误次数', '分类'],
            [
              for (final r in hard)
                [
                  r['word'],
                  r['wrong'],
                  r['promoted'] == true ? '跨天自动提级' : '基础顽固词',
                ],
            ],
            fromExport ? '当日词表见「复习预览」。' : '当日暂无顽固词记录。',
          ),
        ),
        const SizedBox(height: 14),
        Section(
          '未知编码核对',
          Icons.rule,
          table(
            ['ah', 'rh', '评分', '词数', '示例'],
            [
              for (final r in codes)
                [r['ah'], r['rh'], r['rating'], r['count'], r['examples']],
            ],
            data['codes_available'] == true ? '当日没有未知编码。' : '当日缺少词条缓存，无法核对编码。',
          ),
        ),
      ],
    );
  }
}
