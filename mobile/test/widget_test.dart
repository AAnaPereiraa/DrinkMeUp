import 'package:flutter_test/flutter_test.dart';

import 'package:drinkmeup/app.dart';

void main() {
  testWidgets('shows startup loading screen', (WidgetTester tester) async {
    await tester.pumpWidget(const DrinkMeUpApp());
    await tester.pump();

    expect(find.text('Starting DrinkMeUp...'), findsOneWidget);
  });
}
