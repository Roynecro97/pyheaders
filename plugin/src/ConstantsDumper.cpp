#include "clang/AST/AST.h"
#include "clang/AST/ASTConsumer.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendPluginRegistry.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <iomanip>
#include <ios>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>
#include <tuple>

using namespace std;
using namespace clang;

#if __cplusplus < 201402L
using llvm::make_unique;
#endif

// #define DEBUG_PLUGIN
#ifndef DEBUG_PLUGIN
#define DBG(...)
#define DBG_NOTE(...)
#else
#define DBG(expr)                                                      \
    do                                                                 \
    {                                                                  \
        cerr << "\033[33m" #expr ": "                                  \
             << boolalpha << (expr) << boolalpha << "\033[0m" << endl; \
    } while (false)
// ]]

#define DBG_NOTE(expr)                              \
    do                                              \
    {                                               \
        cerr << "\033[32m" #expr "\033[0m" << endl; \
    } while (false)
// ]]
#endif // DEBUG_PLUGIN

namespace
{
//                      val, delim
using CharInfo = tuple<char, char>;
//                          value,          type                context         last
using StructInfo = tuple<const APValue &, const QualType &, const ASTContext &, bool>;
//                          value,          type                context
using ValueInfo = tuple<const APValue &, const QualType &, const ASTContext &>;
//                              record,         last
using RecordInfo = tuple<const CXXRecordDecl *, bool>;

inline constexpr auto char_delim = '\'';
inline constexpr auto string_delim = '"';
inline constexpr auto escape_char = '\\';

static inline bool hasAnyFields(const CXXRecordDecl *decl);

static inline bool baseHasAnyFields(const CXXBaseSpecifier &base)
{
    return hasAnyFields(base.getType()->getAsCXXRecordDecl());
}

static inline bool hasAnyFields(const CXXRecordDecl *decl)
{
    if (decl == nullptr)
    {
        return false;
    }

    if (!decl->field_empty())
    {
        return true;
    }
    return any_of(decl->bases_begin(), decl->bases_end(), baseHasAnyFields);
}

ostream &operator<<(ostream &os, const ValueInfo &value_info);

ostream &operator<<(ostream &os, const CharInfo &char_info)
{
    const auto [value, delim] = char_info;

    if (!isprint(static_cast<unsigned char>(value)))
    {
        os << escape_char;
        const auto old_fill = os.fill('0');
        os << oct << setw(3) << +value;
        os.unsetf(ios_base::oct);
        os.fill(old_fill);
        return os;
    }

    if (value == delim)
    {
        os << escape_char;
    }
    return os << value;
}

ostream &operator<<(ostream &os, const StructInfo &struct_info)
{
    auto &&[value, type, ast_context, last] = struct_info;
    auto *record_decl = type->getAsCXXRecordDecl();

    const auto base_count = value.getStructNumBases();
    const auto field_count = value.getStructNumFields();

    auto base_iter = record_decl->bases_begin();
    auto base_end = record_decl->bases_end();
    for (unsigned i = 0; i < base_count; ++i)
    {
        const auto &base = value.getStructBase(i);

        // The amount of bases in the type should be the same as the one in the value
        // so we shouldn't get into trouble here...
        if (base_iter != base_end)
        {
            const auto &base_type = base_iter->getType();

            const auto last_base_with_fields = i == base_count - 1 || none_of(next(base_iter), base_end, baseHasAnyFields);

            os << StructInfo(base, base_type, ast_context,
                             last_base_with_fields && field_count == 0 && last);
            ++base_iter;
        }
        else
        {
            // No point to continue atm.
            break;
        }
    }

    auto field_iter = record_decl->field_begin();
    auto field_end = record_decl->field_end();
    for (unsigned i = 0; i < field_count; ++i)
    {
        const auto &field = value.getStructField(i);

        // The amount of fields in the type should be the same as the one in the value
        // so we shouldn't get into trouble here...
        if (field_iter != field_end)
        {
            const auto &field_type = field_iter->getType();
            os << ValueInfo(field, field_type, ast_context);
            if (!last || i < field_count - 1)
            {
                os << ",";
            }
            ++field_iter;
        }
        else
        {
            // No point to continue atm.
            break;
        }
    }
    return os;
}

ostream &operator<<(ostream &os, const ValueInfo &value_info)
{
    auto &&[value, type, ast_context] = value_info;

    // Print only literal types
    if (!type->isLiteralType(ast_context))
    {
        return os << "<non-literal>";
    }

    if (type->isFundamentalType())
    {
        if (type->isAnyCharacterType())
        {
            if (type->isCharType())
            {
                // Check that type is not a typedef to make uint8_t print as a number but char as a character.
                // (type == type.getCanonicalType()) // returns false on `char` for some reason
                if (type.getCanonicalType().getAsString() == type.getAsString())
                {
                    return os << char_delim << CharInfo(static_cast<char>(value.getInt().getExtValue()), char_delim) << char_delim;
                }
            }
            else
            {
                return os << type.getCanonicalType().getUnqualifiedType().getAsString() << "(" << value.getAsString(ast_context, type) << ")";
            }
        }
    }
    else
    {
        if (type->isPointerType() && type->getPointeeOrArrayElementType()->isAnyCharacterType())
        {
            const auto str = value.getAsString(ast_context, type);
            // content includes the delimiters
            const auto content_begin = str.find(string_delim);
            const auto content_end = str.rfind(string_delim) + 1;
            return os << str.substr(content_begin, content_end - content_begin);
        }
        if (type->isArrayType())
        {
            const auto array_size = [](const APValue &value, const QualType &type) {
                const auto real_size = value.getArraySize();
                if (type->getPointeeOrArrayElementType()->isAnyCharacterType() && value.getArrayInitializedElt(real_size - 1).getInt() == 0)
                {
                    return real_size - 1;
                }
                return real_size;
            }(value, type); // structured binding cannot be captured
            const auto element_type = QualType(type->getPointeeOrArrayElementType(), Qualifiers::Const);

            // Handle char, signed char, unsigned char (regular strings)
            if (type->getPointeeOrArrayElementType()->isCharType())
            {
                os << string_delim;
                for (unsigned i = 0; i < array_size; ++i)
                {
                    os << CharInfo(static_cast<char>(value.getArrayInitializedElt(i).getInt().getExtValue()), string_delim);
                }
                return os << string_delim;
            }
            // Handle wchar_t, char8_t, char16_t, char32_t (special encoding strings)
            if (type->getPointeeOrArrayElementType()->isAnyCharacterType())
            {
                os << element_type.getCanonicalType().getUnqualifiedType().getAsString() << "[]";
            }

            os << "(";
            for (unsigned i = 0; i < array_size; ++i)
            {
                os << ValueInfo(value.getArrayInitializedElt(i), element_type, ast_context);
                if (i < array_size - 1)
                {
                    os << ",";
                }
            }
            return os << ")";
        }
        if (type->isRecordType() && value.isStruct())
        {
            const auto record_decl = type->getAsCXXRecordDecl();
            if (!record_decl->getNameAsString().empty())
            {
                os << record_decl->getQualifiedNameAsString();
            }
            return os << "(" << StructInfo(value, type, ast_context, true) << ")";
        }
    }

    // Default for all types that don't require special handling (ie: most `int`s, `float`, ...)
    return os << value.getAsString(ast_context, type);
}

ostream &operator<<(ostream &os, const RecordInfo &record_info)
{
    auto &&[decl, last] = record_info;

    const auto empty = decl->field_empty();

    auto base_end = decl->bases_end();
    for (auto base_iter = decl->bases_begin(); base_iter != base_end; ++base_iter)
    {
        auto next_base = next(base_iter);
        const auto last_base_with_fields = next_base == base_end || none_of(next_base, base_end, baseHasAnyFields);

        os << RecordInfo(base_iter->getType()->getAsCXXRecordDecl(),
                         last_base_with_fields && empty && last);
    }

    auto field_end = decl->field_end();
    for (auto field_iter = decl->field_begin(); field_iter != field_end; ++field_iter)
    {
        os << field_iter->getNameAsString();
        if (next(field_iter) != field_end || !last)
        {
            os << ",";
        }
    }
    return os;
}

class ConstantsDumperVisitor : public RecursiveASTVisitor<ConstantsDumperVisitor>
{
public:
    bool VisitEnumDecl(EnumDecl *decl)
    {
        DBG_NOTE(---------------------);
        DBG_NOTE(Enter VisitEnumDecl());

        DBG(decl->getNameAsString());          // bar
        DBG(decl->getQualifiedNameAsString()); // foo::bar
        DBG(decl->getIntegerType().getAsString());

        cout << "enum " << decl->getQualifiedNameAsString() << " {" << endl;
        for (auto &&enum_constant_decl : decl->enumerators())
        {
            cout << enum_constant_decl->getQualifiedNameAsString() << "="
                 << ValueInfo(APValue(enum_constant_decl->getInitVal()), decl->getIntegerType(), decl->getASTContext())
                 << "," << endl;
        }
        cout << "}" << endl;

        DBG_NOTE(Leave VisitEnumDecl());
        DBG_NOTE(---------------------);

        return true;
    }

    bool VisitVarDecl(VarDecl *decl)
    {
        DBG_NOTE(--------------------);
        DBG_NOTE(Enter VisitVarDecl());

        DBG(decl->getNameAsString());                                               // bar
        DBG(decl->getQualifiedNameAsString());                                      // foo::bar
        DBG(decl->getType().getQualifiers().getAsString());                         // const
        DBG(decl->getType().getCanonicalType().getUnqualifiedType().getAsString()); // int
        DBG(decl->getType().getCanonicalType().getAsString());                      // const int
        DBG(decl->getType().getUnqualifiedType().getAsString());                    // int32_t
        DBG(decl->getType().getAsString());                                         // const int32_t
        DBG(decl->getType()->isFundamentalType());
        DBG(decl->getType()->isRecordType());
        DBG(decl->getType()->isLiteralType(decl->getASTContext()));
        DBG(decl->getType()->isArrayType());
        DBG(decl->getType()->isConstantArrayType());
        DBG(decl->getType()->isPointerType());

#ifdef DEBUG_PLUGIN
        if (decl->getType()->isArrayType() || decl->getType()->isPointerType())
        {
            DBG(QualType(decl->getType()->getPointeeOrArrayElementType(), Qualifiers::Const).getAsString());
        }

        if (decl->getType()->isRecordType())
        {
            auto *recordDecl = decl->getType()->getAsCXXRecordDecl();
            DBG(recordDecl->isPOD());
            DBG(recordDecl->isStandardLayout());
            DBG(recordDecl->isCXX11StandardLayout());
            DBG(recordDecl->isLiteral());
            DBG(decl->getType()->getAsRecordDecl()->getBody());
            DBG(decl->getType()->getAsRecordDecl()->getNameAsString());

            DBG(recordDecl->getNameAsString());
            DBG(recordDecl->getQualifiedNameAsString());
        }
        if (decl->getEvaluatedValue())
        {
            DBG(decl->getEvaluatedValue()->getAsString(decl->getASTContext(), decl->getType()));
        }
#endif // DEBUG_PLUGIN

        // Check only literal types
        if (!decl->getType()->isLiteralType(decl->getASTContext()))
        {
            DBG_NOTE(Leave VisitVarDecl()[not literal]);
            DBG_NOTE(--------------------);

            return true;
        }

        // Exclude function parameters
        if (decl->isLocalVarDeclOrParm() && !decl->isLocalVarDecl())
        {
            DBG_NOTE(Leave VisitVarDecl()[local parameter]);
            DBG_NOTE(--------------------);

            return true;
        }

        // Make sure there is an initialization for the variable
        if (!decl->hasInit())
        {
            DBG_NOTE(Leave VisitVarDecl()[no init]);
            DBG_NOTE(--------------------);

            return true;
        }

        if (decl->isConstexpr() || (decl->checkInitIsICE() && decl->isUsableInConstantExpressions(decl->getASTContext())))
        {
            if (decl->getEvaluatedValue() == nullptr)
            {
                DBG_NOTE(Leave VisitVarDecl()[no value]);
                DBG_NOTE(--------------------);

                return true;
            }

#ifdef DEBUG_PLUGIN
            if (decl->getType()->isAnyCharacterType())
            {
                DBG(decl->getType()->isCharType());
                DBG(decl->getType()->isWideCharType());
                DBG(decl->getType()->isChar8Type());
                DBG(decl->getType()->isChar16Type());
                DBG(decl->getType()->isChar32Type());
            }
            if (decl->getEvaluatedValue()->isInt())
            {
                DBG(decl->getEvaluatedValue()->getInt().getExtValue());
                DBG(decl->getEvaluatedValue()->getInt().getSExtValue());
                DBG(decl->getEvaluatedValue()->getInt().getZExtValue());
            }
            if (decl->getEvaluatedValue()->isFloat())
            {
                DBG(decl->getEvaluatedValue()->getFloat().convertToFloat());
                DBG(decl->getEvaluatedValue()->getFloat().convertToDouble());
            }
            if (decl->getEvaluatedValue()->isStruct())
            {
                for (unsigned base_index = 0; base_index < decl->getEvaluatedValue()->getStructNumBases(); ++base_index)
                {
                    DBG(base_index);
                    auto base = decl->getEvaluatedValue()->getStructBase(base_index);

                    for (unsigned base_field_index = 0; base_field_index < base.getStructNumFields(); ++base_field_index)
                    {
                        DBG(base_field_index);
                        auto base_field = base.getStructField(base_field_index);
                        DBG(base_field.getAsString(decl->getASTContext(), decl->getType()));
                    }
                    // DBG(base.getAsString(decl->getASTContext(), decl->getType()));
                }
                for (unsigned field_index = 0; field_index < decl->getEvaluatedValue()->getStructNumFields(); ++field_index)
                {
                    DBG(field_index);
                    auto field = decl->getEvaluatedValue()->getStructField(field_index);
                    DBG(field.getAsString(decl->getASTContext(), decl->getType()));
                }
            }
#endif // DEBUG_PLUGIN

            cout << decl->getQualifiedNameAsString() << "="
                 << ValueInfo(*decl->getEvaluatedValue(), decl->getType(), decl->getASTContext()) << endl;
        }

        DBG_NOTE(Leave VisitVarDecl());
        DBG_NOTE(--------------------);
        return true;
    }
};

class ConstantsDumperConsumer : public ASTConsumer
{
public:
    void HandleTranslationUnit(ASTContext &context)
    {
        visitor.TraverseDecl(context.getTranslationUnitDecl());
    }

private:
    ConstantsDumperVisitor visitor;
};

class ConstantsDumperASTAction : public PluginASTAction
{
public:
    virtual unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &Compiler, llvm::StringRef InFile)
    {
        return make_unique<ConstantsDumperConsumer>();
    }

    bool ParseArgs(const CompilerInstance &CI,
                   const vector<string> &args)
    {
        return true;
    }
};

class LiteralTypesDumperVisitor : public RecursiveASTVisitor<LiteralTypesDumperVisitor>
{
public:
    bool VisitCXXRecordDecl(CXXRecordDecl *decl)
    {
        DBG_NOTE(--------------------------);
        DBG_NOTE(Enter VisitCXXRecordDecl());

        DBG(decl->getNameAsString());          // bar
        DBG(decl->getQualifiedNameAsString()); // foo::bar
        DBG(decl->hasDefinition());
        DBG(decl->isLambda());
        DBG(decl->isTemplated());

        if (decl->getNameAsString().empty())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[anonymous]);
            DBG_NOTE(--------------------------);

            return true;
        }

        if (!decl->hasDefinition())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[no definition]);
            DBG_NOTE(--------------------------);

            return true;
        }

        DBG(decl->isLiteral());

        if (decl->isLambda())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[lambda]);
            DBG_NOTE(--------------------------);

            return true;
        }

        if (!decl->isLiteral())
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[not literal]);
            DBG_NOTE(--------------------------);

            return true;
        }

        if (!hasAnyFields(decl))
        {
            DBG_NOTE(Leave VisitCXXRecordDecl()[empty]);
            DBG_NOTE(--------------------------);

            return true;
        }

#ifdef DEBUG_PLUGIN
        if (decl->getDescribedTemplate())
        {
            DBG(decl->getDescribedTemplate()->getNameAsString());
            DBG(decl->getDescribedTemplate()->getQualifiedNameAsString());
        }

        if (decl->getDescribedClassTemplate())
        {
            DBG(decl->getDescribedClassTemplate()->getNameAsString());
            DBG(decl->getDescribedClassTemplate()->getQualifiedNameAsString());
        }

        for (unsigned i = 0; i < decl->getNumTemplateParameterLists(); ++i)
        {
            DBG(i);
            auto param_list = decl->getTemplateParameterList(i);
            DBG(param_list != nullptr);
            if (param_list)
            {
                DBG(param_list->size());
                for (auto &&param : *param_list)
                {
                    DBG(param->getNameAsString());
                    DBG(param->getQualifiedNameAsString());
                }
            }
        }

        for (auto &&base : decl->bases())
        {
            DBG(base.getType().getQualifiers().getAsString());
            DBG(base.getType().getCanonicalType().getUnqualifiedType().getAsString());
            DBG(base.getType().getCanonicalType().getAsString());
            DBG(base.getType().getUnqualifiedType().getAsString());
            DBG(base.getType().getAsString());
        }

        for (auto &&field : decl->fields())
        {
            DBG(field->getNameAsString());
            DBG(field->getQualifiedNameAsString());
            DBG(field->getType().getQualifiers().getAsString());
            DBG(field->getType().getCanonicalType().getUnqualifiedType().getAsString());
            DBG(field->getType().getCanonicalType().getAsString());
            DBG(field->getType().getUnqualifiedType().getAsString());
            DBG(field->getType().getAsString());
        }
#endif // DEBUG_PLUGIN

        cout << decl->getQualifiedNameAsString() << "{" << RecordInfo(decl, true) << "}" << endl;

        DBG_NOTE(Leave VisitCXXRecordDecl());
        DBG_NOTE(--------------------------);

        return true;
    }
};

class LiteralTypesDumperConsumer : public ASTConsumer
{
public:
    void HandleTranslationUnit(ASTContext &context)
    {
        visitor.TraverseDecl(context.getTranslationUnitDecl());
    }

private:
    LiteralTypesDumperVisitor visitor;
};

class LiteralTypesDumperASTAction : public PluginASTAction
{
public:
    virtual unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &Compiler, llvm::StringRef InFile)
    {
        return make_unique<LiteralTypesDumperConsumer>();
    }

    bool ParseArgs(const CompilerInstance &CI,
                   const vector<string> &args)
    {
        return true;
    }
};
} // namespace

static clang::FrontendPluginRegistry::Add<LiteralTypesDumperASTAction> Y("TypesDumper", "Dumps all class / struct literal types from the code");
static clang::FrontendPluginRegistry::Add<ConstantsDumperASTAction> X("ConstantsDumper", "Dumps all constants and enums from the code");
